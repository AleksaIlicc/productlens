import asyncio
import base64
import io
import json
from functools import lru_cache
from pathlib import Path

from openai import AsyncOpenAI
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ValidationError

from config import get_settings
from products import Product
from schemas import Comparison, ImageFacts
from scraper.http import fetch_image_bytes

# Below this many photos there's nothing meaningful to filter — a page with
# 1-2 images doesn't carry an unrelated-product carousel.
MIN_IMAGES_TO_FILTER = 3

# xAI's vision API hard-rejects anything smaller than this (whole batch
# fails, not just that image) — site icons and tiny thumbnails hit this.
MIN_IMAGE_PIXELS = 512

BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = BACKEND_DIR / "data" / "image_facts.cache.json"

EXTRACT_PROMPT = """You read product photos like a mystery shopper collecting
evidence. Extract ONLY what is actually visible — nothing assumed from general
brand knowledge.

For each image: its filename, its role (e.g. "packaging front", "packaging
back / ingredients label", "marketing banner", "shade swatch"), visible_text
(every readable string, verbatim), and a short note in Serbian.

Then combine everything into one set of facts for the listing: product_name,
shade, volume, ingredients (the INCI list, if visible), warnings (any
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

Check exactly these six dimensions, one result each — no more, no fewer:
product_identity, shade, volume, ingredients, warnings, images_vs_text.

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

IMAGE_FILTER_PROMPT = """A shop page was scraped for one product, but its
photo gallery can include shots of OTHER products — a related-products
carousel, a banner for a different shade/variant, unrelated promo content.

You're given the product's name, then each candidate photo, numbered.
Return the numbers of only the photos that actually show THIS product
(packaging, texture, swatch, or a marketing shot of it — any angle is
fine). Drop photos that clearly show a different product or variant.

If you can't tell whether a photo shows this product, keep it — only drop
photos you're confident are unrelated."""


class _RelevantImages(BaseModel):
    keep: list[int]


@lru_cache
def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY is not set in .env")
    return AsyncOpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


def _big_enough(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return (img.width * img.height) >= MIN_IMAGE_PIXELS
    except UnidentifiedImageError:
        return False


async def _image_part(url: str) -> dict | None:
    data = await fetch_image_bytes(url)
    if data is None or not _big_enough(data):
        return None
    b64 = base64.b64encode(data).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
    }


async def _fetch_all(urls: list[str]) -> dict[str, dict]:
    # Unreachable images are dropped, not fatal: one fewer photo.
    parts = await asyncio.gather(*(_image_part(url) for url in urls))
    return {url: part for url, part in zip(urls, parts) if part is not None}


async def _relevant_images(product: Product, parts: dict[str, dict]) -> list[str]:
    urls = list(parts)
    if len(urls) < MIN_IMAGES_TO_FILTER:
        return urls

    content: list[dict] = [{"type": "text", "text": f"Product: {product.title}"}]
    for index, url in enumerate(urls):
        content.append({"type": "text", "text": f"Photo {index}:"})
        content.append(parts[url])

    completion = await _client().chat.completions.parse(
        model=get_settings().xai_filter_model,
        messages=[
            {"role": "system", "content": IMAGE_FILTER_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format=_RelevantImages,
    )
    result = completion.choices[0].message.parsed
    if not result or not result.keep:
        return urls  # filter call failed to commit to anything — fail open

    kept = [urls[i] for i in result.keep if 0 <= i < len(urls)]
    return kept or urls


def _cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def _cache_store(product_id: str, facts: ImageFacts) -> None:
    # Re-read right before writing: two products are analysed concurrently,
    # so a cache read from the start of the run is already stale by now.
    cache = _cache()
    cache[product_id] = facts.model_dump()
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


_EMPTY_FACTS = ImageFacts(
    per_image=[],
    product_name="",
    shade="",
    volume="",
    ingredients=[],
    warnings=[],
    claims=[],
)


def _restore_urls(facts: ImageFacts, kept: list[str]) -> None:
    # The model echoes back a shortened filename ("image.webp"), sometimes the
    # same one twice. Swap in the URL we actually sent, so the cache and the
    # UI gallery get something fetchable. Findings come back in input order.
    if len(facts.per_image) == len(kept):
        for finding, url in zip(facts.per_image, kept):
            finding.image = url
        return
    by_name = {url.rsplit("/", 1)[-1].split("?")[0]: url for url in kept}
    for finding in facts.per_image:
        name = finding.image.rsplit("/", 1)[-1].split("?")[0]
        finding.image = by_name.get(name, finding.image)


async def extract_image_facts(product: Product, *, refresh: bool = False) -> ImageFacts:
    cache = _cache()
    if not refresh and product.id in cache:
        try:
            return ImageFacts.model_validate(cache[product.id])
        except ValidationError:
            pass  # schema changed since this was cached — re-extract below

    parts = await _fetch_all(product.images)
    if not parts:
        # every image was unreadable — nothing to compare against, not a crash
        return _EMPTY_FACTS

    kept = await _relevant_images(product, parts)
    content: list[dict] = []
    for url in kept:
        content.append({"type": "text", "text": f"Image: {url}"})
        content.append(parts[url])

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

    _restore_urls(facts, kept)
    _cache_store(product.id, facts)
    return facts


def _offer_payload(product: Product, facts: ImageFacts) -> dict:
    return {
        "store": product.source,
        "url": product.url,
        "from_website": {
            "title": product.title,
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
