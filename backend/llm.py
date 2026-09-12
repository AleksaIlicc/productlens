"""Dva LLM koraka: (1) čitanje fotografija, (2) poređenje dve ponude."""

import base64
import json
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from config import get_settings
from products import Product
from schemas import Comparison, ImageFacts

IMAGES_DIR = Path(__file__).parent / "data" / "images"
CACHE_FILE = Path(__file__).parent / "data" / "image_facts.cache.json"

EXTRACT_PROMPT = """Ti si asistent za kontrolu kvaliteta podataka o proizvodima.

Dobijaš fotografije JEDNE prodajne ponude, redom, sa nazivom fajla ispred svake.
Izvuci ISKLJUČIVO ono što se stvarno vidi na slikama (tekst sa ambalaže, deklaracija,
marketinški baneri, swatch nijanse). Ništa ne pretpostavljaj i ništa ne dopunjuj iz
opšteg znanja o brendu.

Za svaku sliku popuni:
- image: naziv fajla
- role: čemu slika služi (npr. "prednja strana ambalaže", "deklaracija/sastav",
  "marketinški baner", "swatch nijanse", "tekstura proizvoda")
- visible_text: svaki čitljiv tekst sa slike, doslovno
- claims: marketinške tvrdnje sa te slike (npr. "16h", "SPF 35", "nekomedogeno")
- notes: kratko zapažanje na srpskom

Zatim popuni objedinjene podatke za celu ponudu (product_name, brand, shade, volume,
spf, claims). Ako nešto nigde nije vidljivo, upiši prazan string odnosno praznu listu.
Piši na srpskom, osim teksta koji doslovno prepisuješ sa ambalaže."""

COMPARE_PROMPT = """Ti si asistent za kontrolu kvaliteta kataloga proizvoda.

Dobijaš dve prodajne ponude istog (navodno) proizvoda sa dva različita sajta. Za svaku
dobijaš: podatke sa sajta (naslov, cena, specifikacija, opisne sekcije) i podatke koje je
vision model pročitao sa fotografija.

Uporedi ih polje po polje i prijavi SVAKO neslaganje. Obavezno pokrij bar:
identitet proizvoda, brend, nijansu, zapreminu/pakovanje, SPF, cenu, šifru/barkod,
sastav (INCI), sadržaj opisa, uputstvo za upotrebu, i slaganje slika sa tekstom.

Pravila:
- value_a je vrednost iz ponude A, value_b iz ponude B; ako vrednosti nema, upiši "—".
- origin: "web" ako polje dolazi sa sajta, "image" ako sa fotografija, "both" ako iz oba.
- status: "match" (isto), "minor" (ista suština, druga formulacija/format),
  "mismatch" (stvarno se razlikuje), "missing" (postoji samo na jednoj strani).
- severity: "high" ako neslaganje znači da je reč o drugom proizvodu ili obmanjuje kupca
  (nijansa, zapremina, SPF, sastav), "medium" za cenu i nedostajuće bitne informacije,
  "low" za formatiranje i stilske razlike, "info" za polja koja se poklapaju.
- explanation: jasno objasni ŠTA je razlika i zašto je bitna. Na srpskom.
- Nemoj prijavljivati isto neslaganje dva puta i nemoj izmišljati polja.

same_product: da li je u pitanju fizički isti artikal. verdict: 2-3 rečenice zaključka
na srpskom."""


@lru_cache
def _client() -> OpenAI:
    settings = get_settings()
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY nije postavljen u .env")
    return OpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


def _image_content(product: Product) -> list[dict]:
    content: list[dict] = []
    for name in product.images:
        data = (IMAGES_DIR / product.id / name).read_bytes()
        b64 = base64.b64encode(data).decode()
        content.append({"type": "text", "text": f"Slika: {name}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
            }
        )
    return content


def _cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def extract_image_facts(product: Product, *, refresh: bool = False) -> ImageFacts:
    """Jedan vision poziv po ponudi; rezultat se kešira na disk."""
    cache = _cache()
    if not refresh and product.id in cache:
        return ImageFacts.model_validate(cache[product.id])

    completion = _client().chat.completions.parse(
        model=get_settings().xai_model,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": _image_content(product)},
        ],
        response_format=ImageFacts,
    )
    facts = completion.choices[0].message.parsed
    if facts is None:
        raise RuntimeError("Model nije vratio strukturirani odgovor za slike")

    cache[product.id] = facts.model_dump()
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return facts


def _offer_payload(product: Product, facts: ImageFacts) -> dict:
    return {
        "prodavnica": product.source,
        "url": product.url,
        "sa_sajta": {
            "naslov": product.title,
            "brend": product.brand,
            "cena": product.price,
            "dostupnost": product.availability,
            "specifikacija": product.specs,
            "sekcije": product.sections,
            "broj_slika": len(product.images),
        },
        "sa_slika": facts.model_dump(),
    }


def compare_products(
    a: Product, b: Product, facts_a: ImageFacts, facts_b: ImageFacts
) -> Comparison:
    payload = {
        "ponuda_A": _offer_payload(a, facts_a),
        "ponuda_B": _offer_payload(b, facts_b),
    }
    completion = _client().chat.completions.parse(
        model=get_settings().xai_model,
        messages=[
            {"role": "system", "content": COMPARE_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format=Comparison,
    )
    comparison = completion.choices[0].message.parsed
    if comparison is None:
        raise RuntimeError("Model nije vratio strukturirani odgovor za poređenje")
    return comparison
