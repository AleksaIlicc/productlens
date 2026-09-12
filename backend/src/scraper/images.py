"""Turn the pile of image URLs a shop page yields into a clean product gallery.

Rules come from real pages (lilly.rs Magento cache hashes, apotekajankovic
OpenCart `-640x640` variants, Exa imageLinks mixing in site chrome).
"""

import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scraper.models import ImageRef
from scraper.urls import absolutize

# Filename/path fragments that are site furniture, never the product.
JUNK_PATTERNS = (
    "logo",
    "sprite",
    "favicon",
    "placeholder",
    "no-image",
    "noimage",
    "no_image",
    "dummy",
    "banner",
    "loader",
    "loading",
    "spinner",
    "payment",
    "visa",
    "mastercard",
    "maestro",
    "paypal",
    "amex",
    "social",
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "whatsapp",
    "viber",
    "twitter",
    "pinterest",
    "flag",
    "badge",
    "sticker",
    "stikeri",
    "renditions",
    "slike-brendova",
    "brand-logo",
    "avatar",
    "captcha",
    "pixel",
    "1x1",
    "blank",
    "spacer",
    "arrow",
    "chevron",
    "star",
    "rating",
    "basket",
    "cart-",
    "wishlist",
    "compare",
    "shipping",
    "truck",
    "gift",
    "newsletter",
    "trustpilot",
    "cookie",
    "/icons/",
    "/icon/",
    "icon-",
    "-icon",
    "_icon",
    "ico-",
    "-ico.",
    "/wysiwyg/",
    "retina_images",
    "e-commerce",
    "/categories/",
    "/kategorije/",
    "/logos/",
    "mail.png",
    "editorial-content",
    "highlight-graphics",
    "/assets/mp/",
)

# Anything ending in these is not a photo we can hand to a vision model.
BAD_EXTENSIONS = (".svg", ".ico", ".css", ".js", ".json", ".mp4", ".webm", ".pdf")

# Size markers inside a filename: -640x640, _800x, x600, @2x, -thumb, -small...
SIZE_SUFFIX_RE = re.compile(
    r"(?:[-_](?:\d{2,4}x\d{2,4}|\d{2,4}x|x\d{2,4})|@\d+x|[-_](?:thumb|thumbnail|small|medium|large|mini|tiny|xs|sm|md|lg|xl))+$",
    re.I,
)
SIZE_IN_URL_RE = re.compile(r"(\d{2,4})\s*[xX]\s*(\d{2,4})")
# Cloudinary/imgproxy style: /f_auto,q_auto,c_fit,h_1200,w_1200/ (dm.rs, dm.de)
TRANSFORM_SEGMENT_RE = re.compile(
    r"^[a-z]{1,2}_[a-z0-9.:]+(?:,[a-z]{1,2}_[a-z0-9.:]+)*$", re.I
)
WH_PARAM_RE = re.compile(r"\b([wh])_(\d{2,4})\b", re.I)
# Magento-style cache busting: /cache/<long hash>/ (and generic long hex segments).
HASH_SEGMENT_RE = re.compile(r"^[0-9a-f]{16,64}$", re.I)
# Resize knobs some CDNs pass in the query string.
SIZE_QUERY_PARAMS = {
    "w",
    "h",
    "width",
    "height",
    "size",
    "resize",
    "fit",
    "crop",
    "quality",
    "q",
    "dpr",
    "scale",
    "format",
    "auto",
}

ROLE_ORDER = {"main": 0, "og": 1, "gallery": 2, "unknown": 3, "search": 4}


def _is_junk(url: str) -> bool:
    low = url.lower()
    if low.startswith("data:") or not low.startswith(("http://", "https://")):
        return True
    parts = urlsplit(low)
    if parts.path.endswith(BAD_EXTENSIONS):
        return True
    # Some CDNs proxy images via ?url=<encoded original> (Next.js image
    # optimizer and similar) — the real filename/extension lives there, not
    # in the proxy's own path.
    inner = dict(parse_qsl(parts.query)).get("url", "")
    if inner.startswith(("http://", "https://")) and urlsplit(inner).path.endswith(
        BAD_EXTENSIONS
    ):
        return True
    return any(p in low for p in JUNK_PATTERNS)


def parsed_size(img: ImageRef) -> tuple[int, int]:
    """Declared size, else the largest WxH marker found in the URL."""
    if img.width and img.height:
        return img.width, img.height
    path = urlsplit(img.url).path
    best = (0, 0)
    for w, h in SIZE_IN_URL_RE.findall(path):
        if int(w) * int(h) > best[0] * best[1]:
            best = (int(w), int(h))
    wh = {k.lower(): int(v) for k, v in WH_PARAM_RE.findall(path)}
    if wh and (wh.get("w", 0) * wh.get("h", 0)) > best[0] * best[1]:
        best = (wh.get("w") or wh.get("h", 0), wh.get("h") or wh.get("w", 0))
    return best


def size_score(img: ImageRef) -> int:
    w, h = parsed_size(img)
    return w * h


def _too_small(img: ImageRef) -> bool:
    w, h = parsed_size(img)
    return bool(w and h and (w < 120 or h < 120))


def identity_key(url: str) -> str:
    """Same asset in different sizes / cache buckets collapses to one key."""
    parts = urlsplit(url.lower())
    segments = [s for s in parts.path.split("/") if s]
    kept: list[str] = []
    for i, seg in enumerate(segments):
        if HASH_SEGMENT_RE.match(seg):
            continue  # /cache/3380650127.../ noise
        if TRANSFORM_SEGMENT_RE.match(seg):
            continue  # resize instructions, not identity
        if (
            seg == "cache"
            and i + 1 < len(segments)
            and HASH_SEGMENT_RE.match(segments[i + 1])
        ):
            continue
        kept.append(seg)
    if kept:
        name = kept[-1]
        stem, dot, _ext = name.rpartition(".")
        stem = stem or name
        # Keep gallery position markers (_1, _2) but drop size markers.
        kept[-1] = SIZE_SUFFIX_RE.sub("", stem) if dot else SIZE_SUFFIX_RE.sub("", name)
    query = [
        (k, v) for k, v in parse_qsl(parts.query) if k.lower() not in SIZE_QUERY_PARAMS
    ]
    query.sort()
    return urlunsplit(("", parts.netloc, "/" + "/".join(kept), urlencode(query), ""))


def clean_gallery(
    images: Iterable[ImageRef],
    *,
    page_url: str,
    max_images: int,
    prefer_token: str = "",
    prefer_tokens: tuple[str, ...] = (),
) -> list[ImageRef]:
    """Absolutize -> drop chrome -> collapse size variants -> order -> cap.

    `prefer_token` is the page's GTIN/SKU. Shops name product files after it
    (lilly.rs, shoppster.rs), so it lets us push the real gallery first and drop
    photos carrying a different EAN, i.e. related-product carousels.
    """
    best: dict[str, tuple[int, int, ImageRef]] = {}
    for order, img in enumerate(images):
        url = absolutize(page_url, img.url)
        if not url or _is_junk(url):
            continue
        candidate = img.model_copy(update={"url": url})
        if _too_small(candidate):
            continue
        key = identity_key(url)
        rank = ROLE_ORDER.get(candidate.role, 3)
        current = best.get(key)
        if current is None:
            best[key] = (order, rank, candidate)
            continue
        prev_order, prev_rank, prev = current
        # Prefer the bigger rendition; keep the earliest role/order metadata.
        winner = candidate if size_score(candidate) > size_score(prev) else prev
        merged = winner.model_copy(
            update={
                "role": prev.role if prev_rank <= rank else candidate.role,
                "width": winner.width or prev.width or candidate.width,
                "height": winner.height or prev.height or candidate.height,
                "source": prev.source or candidate.source,
            }
        )
        best[key] = (min(prev_order, order), min(prev_rank, rank), merged)

    entries = list(best.values())
    tokens = [
        t.strip().lower()
        for t in (prefer_token, *prefer_tokens)
        if t and len(t.strip()) >= 5
    ]

    def matches_product(img: ImageRef) -> bool:
        low = img.url.lower()
        return any(token in low for token in tokens)

    if tokens:
        own = [e for e in entries if matches_product(e[2])]
        # Two or more hits means this shop really does name files after the
        # product, so anything unnamed is a related-product or promo image.
        if len(own) >= 2:
            kept = [
                e
                for e in entries
                if matches_product(e[2]) or e[2].role in ("main", "og")
            ]
            kept.sort(key=lambda e: (not matches_product(e[2]), e[1], e[0]))
            return [img for _, _, img in kept][:max_images]

    ordered = sorted(entries, key=lambda item: (item[1], item[0]))
    return [img for _, _, img in ordered][:max_images]


def gallery_urls(images: list[ImageRef], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for img in images:
        if img.url in seen:
            continue
        seen.add(img.url)
        out.append(img.url)
        if len(out) >= limit:
            break
    return out
