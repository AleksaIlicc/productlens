import base64
import json
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from config import get_settings
from products import Product
from schemas import Comparison, ImageFacts

BACKEND_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BACKEND_DIR / "data" / "images"
CACHE_FILE = BACKEND_DIR / "data" / "image_facts.cache.json"

EXTRACT_PROMPT = """You are a quality-control assistant for product data.

You are given photos of a single product listing, in order, each preceded by its
filename. Extract ONLY what is actually visible in the images (text on the packaging,
the ingredients label, marketing banners, shade swatches). Do not assume or fill in
anything from general brand knowledge.

For each image, fill in:
- image: the filename
- role: what the image shows (e.g. "front of the packaging", "ingredients label",
  "marketing banner", "shade swatch", "product texture")
- visible_text: every piece of readable text on the image, verbatim
- claims: marketing claims shown on that image (e.g. "16h", "SPF 35", "non-comedogenic")
- notes: a short observation, written in Serbian

Then fill in the combined facts for the whole listing (product_name, brand, shade,
volume, spf, claims). If something isn't visible anywhere, use an empty string or an
empty list. Write in Serbian, except for text you copy verbatim from the packaging."""

COMPARE_PROMPT = """You are a quality-control assistant for a product catalog.

You are given two listings of the same (allegedly) product from two different
websites. For each one you get: the data scraped from the site (title, price, specs,
description sections) and the data a vision model read from the photos.

Compare them field by field and report EVERY discrepancy. You must cover at least:
product identity, brand, shade, volume/packaging, SPF, price, SKU/barcode,
ingredients (INCI), description content, usage instructions, and whether the images
match the text.

Rules:
- value_a is the value from listing A, value_b from listing B; use "—" if missing.
- origin: "web" if the field comes from the site, "image" if from the photos, "both"
  if from both.
- status: "match" (identical), "minor" (same substance, different wording/format),
  "mismatch" (actually different), "missing" (present on only one side).
- severity: "high" if the mismatch means it's a different product or misleads the
  buyer (shade, volume, SPF, ingredients), "medium" for price and missing important
  information, "low" for formatting/style differences, "info" for matching fields.
- explanation: clearly explain WHAT the difference is and why it matters. Write in
  Serbian.
- Don't report the same discrepancy twice and don't invent fields.

same_product: whether this is physically the same item. verdict: a 2-3 sentence
conclusion, written in Serbian."""


@lru_cache
def _client() -> OpenAI:
    settings = get_settings()
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY is not set in .env")
    return OpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


def _image_content(product: Product) -> list[dict]:
    content: list[dict] = []
    for name in product.images:
        data = (IMAGES_DIR / product.id / name).read_bytes()
        b64 = base64.b64encode(data).decode()
        content.append({"type": "text", "text": f"Image: {name}"})
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
            "price": product.price,
            "availability": product.availability,
            "specs": product.specs,
            "sections": product.sections,
            "image_count": len(product.images),
        },
        "from_images": facts.model_dump(),
    }


def compare_products(
    a: Product, b: Product, facts_a: ImageFacts, facts_b: ImageFacts
) -> Comparison:
    payload = {
        "listing_a": _offer_payload(a, facts_a),
        "listing_b": _offer_payload(b, facts_b),
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
        raise RuntimeError("Model did not return a structured comparison")
    return comparison
