import base64
import json
from functools import lru_cache
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import ValidationError

from config import get_settings
from products import Product
from schemas import Comparison, ImageFacts
from scraper.http import fetch_image_bytes

BACKEND_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BACKEND_DIR / "data" / "images"
CACHE_FILE = BACKEND_DIR / "data" / "image_facts.cache.json"

EXTRACT_PROMPT = """You read product photos like a mystery shopper collecting
evidence. Extract ONLY what is actually visible — nothing assumed from general
brand knowledge.

For each image: its filename, its role (e.g. "packaging front", "packaging
back / ingredients label", "marketing banner", "shade swatch"), visible_text
(every readable string, verbatim), and a short note in Serbian.

Then combine everything into one set of facts for the listing: product_name,
brand, shade, volume, ingredients (the INCI list, if visible), warnings (any
safety/allergy claim), and claims (other marketing claims, e.g. "16h",
"SPF 35"). Use an empty string or empty list for anything not visible. Write
in Serbian, except for text copied verbatim from the packaging."""

COMPARE_PROMPT = """You audit whether a retailer's product listing matches the
brand's official content — a mystery shopper checking for a mislabeled shade,
wrong volume, missing ingredients or safety warnings, and photos that don't
match the listing text. Price, availability, SKU and category are out of
scope: don't mention them.

You get two listings of the same (allegedly) product: text scraped from each
site plus facts a vision model read from each one's photos.

Check exactly these seven dimensions, one result each — no more, no fewer:
product_identity, brand, shade, volume, ingredients, warnings, images_vs_text.

For each dimension:
- value_a / value_b: what each listing states; "—" if not stated at all.
- origin: "web", "image", or "both".
- status: "match", "minor" (same substance, different wording), "mismatch"
  (materially different), "missing" (stated on only one side).
- severity: "high" if it could mislead a buyer or is a compliance risk (wrong
  shade, wrong volume, missing ingredients/warnings), "medium" for a real gap,
  "low" for a wording nuance, "info" only when you must report a match anyway.
- explanation: what differs and why it matters, in Serbian.

If you're not sure something actually differs, mark it "match" rather than
guessing — don't invent findings.

same_product: whether this is physically the same item. verdict: a 2-3
sentence summary, in Serbian."""


@lru_cache
def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY is not set in .env")
    return AsyncOpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


async def _image_part(product: Product, name: str) -> dict | None:
    """One image as a data: URL, or None if it couldn't be read.

    `name` is a local filename for the hardcoded demo products, or a full
    remote URL for a live-scraped offer — either way we just need bytes.
    """
    if name.startswith(("http://", "https://")):
        data = await fetch_image_bytes(name)
        if data is None:
            return None  # dead link / blocked host — skip it, don't fail the run
    else:
        path = IMAGES_DIR / product.id / name
        if not path.is_file():
            return None
        data = path.read_bytes()

    b64 = base64.b64encode(data).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
    }


async def _image_content(product: Product) -> list[dict]:
    content: list[dict] = []
    for name in product.images:
        part = await _image_part(product, name)
        if part is None:
            continue
        content.append({"type": "text", "text": f"Image: {name}"})
        content.append(part)
    return content


def _cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


_EMPTY_FACTS = {
    "per_image": [],
    "product_name": "",
    "brand": "",
    "shade": "",
    "volume": "",
    "ingredients": [],
    "warnings": [],
    "claims": [],
}


async def extract_image_facts(product: Product, *, refresh: bool = False) -> ImageFacts:
    cache = _cache()
    if not refresh and product.id in cache:
        try:
            return ImageFacts.model_validate(cache[product.id])
        except ValidationError:
            pass  # schema changed since this was cached — re-extract below

    content = await _image_content(product)
    if not content:
        # every image was unreadable — nothing to compare against, not a crash
        return ImageFacts.model_validate(_EMPTY_FACTS)

    completion = await _client().chat.completions.parse(
        model=get_settings().xai_model,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format=ImageFacts,
    )
    facts = completion.choices[0].message.parsed
    if facts is None:
        raise RuntimeError("Model did not return structured image facts")

    cache[product.id] = facts.model_dump()
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    return facts


def _offer_payload(product: Product, facts: ImageFacts) -> dict:
    return {
        "store": product.source,
        "url": product.url,
        "from_website": {
            "title": product.title,
            "brand": product.brand,
            "text": product.raw_text,
        },
        "from_images": facts.model_dump(),
    }


async def compare_products(
    a: Product, b: Product, facts_a: ImageFacts, facts_b: ImageFacts
) -> Comparison:
    payload = {
        "listing_a": _offer_payload(a, facts_a),
        "listing_b": _offer_payload(b, facts_b),
    }
    completion = await _client().chat.completions.parse(
        model=get_settings().xai_model,
        messages=[
            {"role": "system", "content": COMPARE_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format=Comparison,
    )
    comparison = completion.choices[0].message.parsed
    if comparison is None:
        raise RuntimeError("Model did not return a structured comparison")
    return comparison
