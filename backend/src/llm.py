import asyncio
import base64
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ValidationError

from config import get_settings
from products import Product
from schemas import AnalysedListing, Comparison, ImageFacts, ListingValue
from scraper.http import fetch_image_bytes

# Below this many photos there's nothing meaningful to filter — a page with
# 1-2 images doesn't carry an unrelated-product carousel.
MIN_IMAGES_TO_FILTER = 3

# One unusable image fails the whole batch, not just that image, so both of
# these are checked before sending: the API rejects anything smaller than
# MIN_IMAGE_PIXELS (site icons, tiny thumbnails), and it only decodes the
# formats below — while Pillow happily opens GIF/BMP/AVIF that it can't.
MIN_IMAGE_PIXELS = 512
SUPPORTED_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = BACKEND_DIR / "data" / "image_facts.cache.json"

EXTRACT_PROMPT = """You read product photos like a mystery shopper collecting
evidence. Extract ONLY what is actually visible — nothing assumed from general
brand knowledge.

For each image: its filename, its role (e.g. "packaging front", "packaging
back / ingredients label", "marketing banner", "shade swatch"), visible_text
(every readable string, verbatim), and a short note in English.

Then combine everything into one set of facts for the listing: product_name,
shade, volume, ingredients (the INCI list, if visible), warnings (any
safety/allergy claim), and claims (other marketing claims, e.g. "16h",
"SPF 35"). Use an empty string or empty list for anything not visible. Write
in English, except for text copied verbatim from the packaging."""

COMPARE_PROMPT = """You audit whether the same product is described
consistently across every channel that sells it — a mystery shopper checking
for a mislabeled shade, wrong volume, missing ingredients or safety warnings,
and photos that don't match the listing text. Price, availability, SKU and
category are out of scope: don't mention them.

You get two or more listings of the same (allegedly) product, each with a
label (A, B, C, ...): text scraped from that site plus facts a vision model
read from that listing's photos.

Check exactly these six dimensions, one result each — no more, no fewer:
product_identity, shade, volume, ingredients, warnings, images_vs_text.

For each dimension:
- values: ONE entry per listing you were given, using that listing's exact
  label. Never skip a listing, never invent a label. The value is what that
  listing states, condensed; "—" if it does not state it at all.
- flagged: the labels that carry the problem — the listings someone would
  have to go and fix. Where one channel states something different from the
  others, that is the odd one out. For images_vs_text it is every listing
  whose own photos contradict its own text, however many that is. Empty when
  nothing is wrong.
- origin: "web", "image", or "both".
- status: "match" (all listings agree), "minor" (same substance, different
  wording), "mismatch" (at least one is materially different), "missing"
  (stated by some listings and not others).
- severity: "high" if it could mislead a buyer or is a compliance risk (wrong
  shade, wrong volume, missing ingredients/warnings), "medium" for a real gap,
  "low" for a wording nuance, "info" only when you must report a match anyway.
- explanation: which listings differ and why it matters, in English. Name them
  by label and shop, e.g. "C (lilly.rs) says 35 Sand while A and B say 30
  Beige".

If you're not sure something actually differs, mark it "match" rather than
guessing — don't invent findings.

same_product: whether every listing is physically the same item. verdict: a
2-3 sentence summary of where the channels disagree, in English."""

IMAGE_FILTER_PROMPT = """A shop page was scraped for one product, but its
photo gallery can include shots of a completely DIFFERENT product — a
related-products carousel, an unrelated promo — or site chrome: logos,
icons, payment badges, QR codes.

You're given the product's name, then each candidate photo, numbered.
Return the numbers of every photo that belongs to THIS product's listing.

Keep a photo of the same product line even when it pictures a different
shade, size or variant than the name says. A shop advertising the wrong
variant is exactly what the next step has to report, so it has to see
those photos — don't quietly remove them.

Drop only photos of a genuinely different product, and site chrome. If
you're unsure, keep it."""


class _RelevantImages(BaseModel):
    keep: list[int]


def _silent(stage: str, message: str, **_: Any) -> None:
    return None


def _plural(count: int, noun: str, suffix: str = "s") -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}{suffix}"


@lru_cache
def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.xai_api_key:
        raise RuntimeError("XAI_API_KEY is not set in .env")
    return AsyncOpenAI(api_key=settings.xai_api_key, base_url=settings.xai_base_url)


def _image_type(data: bytes) -> str | None:
    # The media type to send it as, or None if the API can't use this image.
    try:
        with Image.open(io.BytesIO(data)) as img:
            if (img.width * img.height) < MIN_IMAGE_PIXELS:
                return None
            return SUPPORTED_IMAGE_TYPES.get(img.format or "")
    except UnidentifiedImageError:
        return None


async def _image_part(url: str) -> dict | None:
    data = await fetch_image_bytes(url)
    if data is None:
        return None
    media_type = _image_type(data)
    if media_type is None:
        return None
    b64 = base64.b64encode(data).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "high"},
    }


async def _fetch_all(urls: list[str]) -> dict[str, dict]:
    # Unreachable images are dropped, not fatal: one fewer photo.
    parts = await asyncio.gather(*(_image_part(url) for url in urls))
    return {url: part for url, part in zip(urls, parts) if part is not None}


async def _relevant_images(
    product: Product, parts: dict[str, dict], progress=_silent
) -> list[str]:
    urls = list(parts)
    if len(urls) < MIN_IMAGES_TO_FILTER:
        return urls

    progress(
        "vision",
        f"Screening {_plural(len(urls), 'photo')} from {product.source}",
        detail="shop galleries mix in other products and shades",
        source=product.source,
    )

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
    if kept and len(kept) < len(urls):
        progress(
            "vision",
            f"{product.source}: dropped "
            f"{_plural(len(urls) - len(kept), 'unrelated photo')}",
            detail=f"{_plural(len(kept), 'photo')} left showing this product",
            source=product.source,
        )
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


async def extract_image_facts(
    product: Product, *, refresh: bool = False, progress=_silent
) -> ImageFacts:
    cache = _cache()
    if not refresh and product.id in cache:
        try:
            facts = ImageFacts.model_validate(cache[product.id])
            progress(
                "vision",
                f"{product.source}: reusing an earlier photo read",
                detail=f"{_plural(len(facts.per_image), 'photo')} already analysed",
                tone="ok",
                source=product.source,
            )
            return facts
        except ValidationError:
            pass  # schema changed since this was cached — re-extract below

    progress(
        "vision",
        f"Downloading {_plural(len(product.images), 'photo')} "
        f"from {product.source}",
        source=product.source,
        images=product.images[:12],
    )
    parts = await _fetch_all(product.images)
    if not parts:
        # every image was unreadable — nothing to compare against, not a crash
        progress(
            "vision",
            f"{product.source}: no readable photos",
            detail="every image failed to download or was too small",
            tone="warn",
            source=product.source,
        )
        return _EMPTY_FACTS

    kept = await _relevant_images(product, parts, progress)
    progress(
        "vision",
        f"Reading packaging text on {_plural(len(kept), 'photo')} "
        f"from {product.source}",
        detail=get_settings().xai_model,
        source=product.source,
    )
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
    progress(
        "vision",
        f"{product.source}: read {_plural(len(facts.per_image), 'photo')}",
        detail=", ".join(
            filter(None, [facts.product_name, facts.shade, facts.volume])
        )
        or "nothing legible on the packaging",
        tone="ok",
        source=product.source,
    )
    return facts


def _listing_payload(listing: AnalysedListing) -> dict:
    return {
        "label": listing.label,
        "store": listing.product.source,
        "url": listing.product.url,
        "from_website": {
            "title": listing.product.title,
            "text": listing.product.raw_text,
        },
        "from_images": listing.facts.model_dump(),
    }


def _repair_values(
    comparison: Comparison, listings: list[AnalysedListing]
) -> Comparison:
    """Make every dimension carry exactly one value per listing.

    Structured output gets the labels right almost always, but a dropped or
    hallucinated label would silently misalign a whole column in the report,
    so the set is forced back to the listings we actually sent.
    """
    labels = [listing.label for listing in listings]
    known = set(labels)
    for field in comparison.fields:
        stated = {value.listing: value.value for value in field.values}
        field.values = [
            ListingValue(listing=label, value=stated.get(label, "—"))
            for label in labels
        ]
        field.flagged = [label for label in field.flagged if label in known]
    return comparison


async def compare_listings(
    listings: list[AnalysedListing], progress=_silent
) -> Comparison:
    progress(
        "audit",
        f"Cross-checking {len(listings)} listings",
        detail="identity, shade, volume, ingredients, warnings, photos vs text",
        listings=[listing.product.source for listing in listings],
    )
    payload = {"listings": [_listing_payload(listing) for listing in listings]}
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
    comparison = _repair_values(comparison, listings)

    flagged = [f for f in comparison.fields if f.status != "match"]
    progress(
        "audit",
        f"{len(flagged)} of {len(comparison.fields)} dimensions flagged",
        detail=", ".join(f.field.replace("_", " ") for f in flagged)
        or "every listing agrees on every dimension",
        tone="warn" if flagged else "ok",
    )
    return comparison
