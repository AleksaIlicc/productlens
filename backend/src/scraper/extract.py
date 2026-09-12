# Deterministic extraction, no LLM. Per field the ladder is
# JSON-LD -> microdata -> meta/og -> markdown regex: some shops ship no
# JSON-LD at all (lilly.rs, benu.rs), others do (apotekajankovic.rs, notino).

import json
import re
import unicodedata
from html import unescape
from typing import Any

from scraper.models import ExtractSource, PageFacts, PriceInfo

LD_JSON_RE = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)
ITEMPROP_RE = re.compile(
    r'itemprop\s*=\s*["\']([\w:]+)["\'][^>]*?(?:content\s*=\s*["\']([^"\']*)["\'])?',
    re.I,
)

CURRENCY_TOKENS = {
    "rsd": "RSD",
    "din": "RSD",
    "дин": "RSD",
    "динара": "RSD",
    "eur": "EUR",
    "€": "EUR",
    "usd": "USD",
    "$": "USD",
    "gbp": "GBP",
    "£": "GBP",
    "pln": "PLN",
    "zł": "PLN",
    "zl": "PLN",
    "chf": "CHF",
    "hrk": "HRK",
    "bam": "BAM",
    "km": "BAM",
    "mkd": "MKD",
    "czk": "CZK",
    "kč": "CZK",
    "huf": "HUF",
    "ron": "RON",
    "bgn": "BGN",
}

# Grouped forms first, plain number last: otherwise "18349.0" matches as "183".
NUMBER_PATTERN = (
    r"\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?"  # 1.899,00 / 18 349
    r"|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"  # 1,899.00
    r"|\d+(?:[.,]\d{1,2})?"  # 18349.0 / 2990 / 24,21
)
CURRENCY_PATTERN = r"RSD|EUR|USD|GBP|PLN|CHF|BAM|KM|din\.?|дин\.?|€|\$|£|zł"
PRICE_NEAR_CURRENCY_RE = re.compile(
    r"(?:(?P<cur1>" + CURRENCY_PATTERN + r")\s*)?"
    r"(?P<num>" + NUMBER_PATTERN + r")"
    r"\s*(?P<cur2>" + CURRENCY_PATTERN + r")?",
    re.I,
)

AVAILABILITY_PATTERNS = (
    (
        r"nema\s+na\s+stanju|nije\s+dostupn|trenutno\s+nedostupn|rasprodato|out\s+of\s+stock|outofstock",
        "Nema na stanju",
    ),
    (
        r"na\s+stanju|dostupno|raspolo[žz]ivo|in\s*stock|instock|na\s+lageru",
        "Na stanju",
    ),
    (r"po\s+narud[žz]bi|preorder|uskoro", "Po narudžbini"),
)

SKU_LABEL_RE = re.compile(
    r"(?:[ŠS]ifra(?:\s+proizvoda)?|SKU|Kod\s+proizvoda|Kataloški\s+broj|Art(?:ikal)?\.?\s*br\.?|Product\s+code)"
    r"\s*[:\-]?\s*([A-Za-z0-9._/\-]{3,32})",
    re.I,
)
GTIN_LABEL_RE = re.compile(
    r"(?:EAN(?:-?13)?|GTIN(?:-?1[34])?|Barkod|Bar\s?kod|Barcode)\s*[:\-]?\s*(\d{8,14})",
    re.I,
)
DIGITS13_RE = re.compile(r"(?<!\d)(\d{13})(?!\d)")

VARIANT_PATTERNS = (
    r"\bSPF\s*\d{1,2}\+?\b",
    r"\b\d+(?:[.,]\d+)?\s?(?:ml|l|L|g|gr|kg|mg|cm|mm|m|W|V|Ah|kom|tbl|kapsul[ae]?|komada)\b",
    r"\b\d{1,3}\s+[A-ZČĆŠŽĐ][a-zčćšžđ]{2,}\b",
    r"\bbr(?:oj)?\.?\s*\d{1,3}\b",
    r"\bnijansa\s+\S+\b",
    r"\b\d{1,2}V\b",
)

# Key fragments that mark store chrome, not product data: shops put their
# company registration, opening hours and delivery table in the same
# key: value shape the specs regex below looks for. Diacritics are folded
# away before matching, so plain ASCII spellings are enough here.
JUNK_SPEC_KEYS = (
    "radno vreme",
    "radnim danima",
    "vikendom",
    "po-pia",
    "pon-pet",
    "otvaraci",
    "poslovno ime",
    "sediste",
    "maticni broj",
    "pib",
    "pdv broj",
    "nadlezni",
    "adresa",
    "kontakt",
    "telefon",
    "e-mail",
    "email",
    "web adresa",
    "webova stranka",
    "ico",
    "dostava",
    "isporuka",
    "prodavac",
    "paketomat",
    "paket zona",
    "delivery",
    "shipping",
    "returns",
    "ends in",
    "popust",
    "zlava",
    "cena",
    "price",
    "credit",
    "related",
)

MD_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
KEY_VALUE_RE = re.compile(
    r"^\s*([A-Za-zČĆŠŽĐčćšžđ][\w \-/()%.]{2,40})\s*[:：]\s*(.{1,200})$"
)

PRODUCT_PATH_HINTS = (
    "/product/",
    "/products/",
    "/proizvod/",
    "/proizvodi/",
    "/artikal/",
    "/kupi/",
    "/dp/",
    "/gp/product/",
    "/itm/",
    "/p/",
    "/item/",
    "/shop/",
)
CATEGORY_PATH_HINTS = (
    "/kategorija",
    "/kategorije",
    "/category",
    "/categories",
    "/brend",
    "/brand",
    "/linija",
    "/kolekcija",
    "/c/",
    "/collections/",
    "/listing",
    "/search",
    "/pretraga",
    "/asortiman",
    "/akcije",
)
ARTICLE_PATH_HINTS = (
    "/blog",
    "/savet",
    "/saveti",
    "/clanak",
    "/članak",
    "/news",
    "/vesti",
    "/magazin",
    "/nega-",
)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com")
MARKETPLACE_HOSTS = (
    "amazon.",
    "ebay.",
    "allegro.",
    "aliexpress.",
    "etsy.",
    "kupujemprodajem.com",
    "limundo.com",
    "kupindo.com",
)
COMPARISON_HOSTS = (
    "ceneo.",
    "ceneje.",
    "jeftinije.",
    "idealo.",
    "pricerunner.",
    "skroutz.",
    "google.com/shopping",
    "cenoteka.",
)


# --------------------------------------------------------------------- numbers


def _clean_number(raw: str) -> float | None:
    # "1.899,00" -> 1899.0, "1,899.00" -> 1899.0, "2.340" -> 2340.0
    text = raw.strip().replace(" ", "").replace(" ", "")
    if not text:
        return None
    has_dot, has_comma = "." in text, "," in text
    try:
        if has_dot and has_comma:
            # The rightmost separator is the decimal one.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif has_comma:
            decimals = len(text.rsplit(",", 1)[1])
            text = text.replace(",", "." if decimals <= 2 else "")
        elif has_dot:
            decimals = len(text.rsplit(".", 1)[1])
            # "2.340" is thousands (RSD prices have no cents); "24.21" is decimal.
            if decimals == 3:
                text = text.replace(".", "")
        return float(text)
    except (ValueError, IndexError):
        return None


def _currency_from(token: str | None) -> str:
    if not token:
        return ""
    return CURRENCY_TOKENS.get(token.strip().lower().rstrip("."), "")


def parse_price(raw: Any, *, currency_hint: str = "") -> PriceInfo:
    if raw is None:
        return PriceInfo()
    text = str(raw).strip()
    if not text:
        return PriceInfo()

    currency = _currency_from(currency_hint) or currency_hint.upper()[:3]
    match = PRICE_NEAR_CURRENCY_RE.search(text)
    if not match:
        return PriceInfo(raw=text, currency=currency)
    amount = _clean_number(match.group("num"))
    found_currency = _currency_from(match.group("cur1")) or _currency_from(
        match.group("cur2")
    )
    return PriceInfo(raw=text, amount=amount, currency=found_currency or currency)


def valid_gtin(digits: str) -> bool:
    # GS1 mod-10, so a random 13-digit number isn't mistaken for an EAN.
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = 0
    for i, ch in enumerate(reversed(body)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - total % 10) % 10 == check


# ------------------------------------------------------------------- json-ld


def _iter_ld_nodes(blob: Any):
    if isinstance(blob, list):
        for item in blob:
            yield from _iter_ld_nodes(item)
    elif isinstance(blob, dict):
        yield blob
        for key in ("@graph", "itemListElement", "offers", "mainEntity", "hasVariant"):
            if key in blob:
                yield from _iter_ld_nodes(blob[key])


def _ld_types(node: dict) -> list[str]:
    raw = node.get("@type") or node.get("type") or []
    if isinstance(raw, str):
        return [raw.lower()]
    return [str(t).lower() for t in raw if isinstance(t, (str, bytes))]


def parse_json_ld(html: str) -> list[dict]:
    nodes: list[dict] = []
    for block in LD_JSON_RE.findall(html or ""):
        text = unescape(block).strip()
        if not text:
            continue
        try:
            nodes.extend(_iter_ld_nodes(json.loads(text)))
        except ValueError:
            # Some shops emit trailing commas or concatenated objects; try the
            # largest {...} slice before giving up.
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    nodes.extend(_iter_ld_nodes(json.loads(text[start : end + 1])))
                except ValueError:
                    continue
    return nodes


def _from_json_ld(nodes: list[dict], facts: PageFacts) -> bool:
    used = False
    for node in nodes:
        types = _ld_types(node)
        if "product" in types:
            used = True
            facts.title = facts.title or str(node.get("name") or "")[:300]
            brand = node.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            facts.brand = facts.brand or str(brand or "")[:120]
            facts.sku = facts.sku or str(node.get("sku") or node.get("mpn") or "")[:64]
            for key in ("gtin13", "gtin", "gtin12", "gtin14", "gtin8", "ean"):
                value = str(node.get(key) or "").strip()
                if value and valid_gtin(value):
                    facts.gtin = facts.gtin or value
                    break
            if not facts.description and node.get("description"):
                facts.description = re.sub(
                    r"\s+", " ", unescape(str(node["description"]))
                )[:4000]
        if "offer" in types or "aggregateoffer" in types:
            used = True
            currency = str(node.get("priceCurrency") or "")
            raw_price = (
                node.get("price") or node.get("lowPrice") or node.get("highPrice")
            )
            if raw_price is not None and facts.price.amount is None:
                facts.price = parse_price(raw_price, currency_hint=currency)
            availability = str(node.get("availability") or "")
            if availability and not facts.availability:
                facts.availability = (
                    "Na stanju"
                    if "instock" in availability.lower().replace("_", "")
                    else "Nema na stanju"
                )
        if "breadcrumblist" in types and not facts.breadcrumbs:
            crumbs: list[str] = []
            for element in node.get("itemListElement") or []:
                if isinstance(element, dict):
                    item = element.get("item")
                    name = element.get("name") or (
                        item.get("name") if isinstance(item, dict) else None
                    )
                    if name:
                        crumbs.append(str(name)[:80])
            facts.breadcrumbs = crumbs[:8]
    return used


# ------------------------------------------------------------------ microdata


def _from_microdata(html: str, facts: PageFacts) -> bool:
    if not html:
        return False
    used = False
    props: dict[str, str] = {}
    for name, content in ITEMPROP_RE.findall(html):
        key = name.lower()
        if content and key not in props:
            props[key] = unescape(content).strip()
    if "price" in props and facts.price.amount is None:
        facts.price = parse_price(
            props["price"], currency_hint=props.get("pricecurrency", "")
        )
        used = True
    if "availability" in props and not facts.availability:
        facts.availability = (
            "Na stanju"
            if "instock" in props["availability"].lower().replace("_", "")
            else "Nema na stanju"
        )
        used = True
    for key, target in (
        ("sku", "sku"),
        ("gtin13", "gtin"),
        ("brand", "brand"),
        ("name", "title"),
    ):
        value = props.get(key, "")
        if value and not getattr(facts, target):
            if target == "gtin" and not valid_gtin(value):
                continue
            setattr(facts, target, value[:300])
            used = True
    return used


# ------------------------------------------------------------------ meta tags


META_PRICE_KEYS = (
    "product:price:amount",
    "og:price:amount",
    "price",
    "productprice",
    "twitter:data1",
)
META_CURRENCY_KEYS = (
    "product:price:currency",
    "og:price:currency",
    "pricecurrency",
    "currency",
)
META_TITLE_KEYS = ("og:title", "ogtitle", "title", "twitter:title")
META_DESC_KEYS = (
    "og:description",
    "ogdescription",
    "description",
    "twitter:description",
)
META_BRAND_KEYS = ("brand", "product:brand", "og:brand")
META_SKU_KEYS = ("productid", "product:retailer_item_id", "sku", "product:sku")
META_AVAIL_KEYS = ("product:availability", "og:availability", "availability")


def _first_meta(metadata: dict[str, str], keys: tuple[str, ...]) -> str:
    lower = {k.lower(): v for k, v in metadata.items() if isinstance(v, str)}
    for key in keys:
        value = lower.get(key)
        if value and value.strip():
            return value.strip()
    return ""


def _from_meta(metadata: dict[str, str], facts: PageFacts) -> bool:
    used = False
    title = _first_meta(metadata, META_TITLE_KEYS)
    if title and not facts.title:
        facts.title, used = title[:300], True
    brand = _first_meta(metadata, META_BRAND_KEYS)
    if brand and not facts.brand:
        facts.brand, used = brand[:120], True
    sku = _first_meta(metadata, META_SKU_KEYS)
    if sku and not facts.sku:
        facts.sku, used = sku[:64], True
    description = _first_meta(metadata, META_DESC_KEYS)
    if description and not facts.description:
        facts.description = re.sub(r"\s+", " ", description)[:4000]
        used = True
    availability = _first_meta(metadata, META_AVAIL_KEYS)
    if availability and not facts.availability:
        facts.availability = (
            "Na stanju"
            if "instock" in availability.lower().replace(" ", "").replace("_", "")
            else availability[:60]
        )
        used = True
    raw_price = _first_meta(metadata, META_PRICE_KEYS)
    if raw_price and facts.price.amount is None:
        currency = _first_meta(metadata, META_CURRENCY_KEYS)
        parsed = parse_price(raw_price, currency_hint=currency)
        if parsed.amount is not None:
            facts.price, used = parsed, True
    return used


# ------------------------------------------------------------------- markdown


def _markdown_prices(markdown: str) -> list[PriceInfo]:
    # Only prices next to a currency token; plain numbers are too noisy.
    found: list[PriceInfo] = []
    seen: set[float] = set()
    for match in PRICE_NEAR_CURRENCY_RE.finditer(markdown):
        if not (match.group("cur1") or match.group("cur2")):
            continue
        info = parse_price(match.group(0))
        if info.amount is None or info.amount <= 0 or info.amount in seen:
            continue
        seen.add(info.amount)
        found.append(info)
        if len(found) >= 8:
            break
    return found


def _junk_spec(key: str) -> bool:
    folded = unicodedata.normalize("NFKD", key.replace("đ", "d").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return any(j in folded for j in JUNK_SPEC_KEYS)


def _markdown_specs(markdown: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    for line in markdown.splitlines():
        row = MD_TABLE_ROW_RE.match(line)
        if row:
            cells = [c.strip() for c in row.group(1).split("|")]
            cells = [c for c in cells if c and not set(c) <= {"-", ":", " "}]
            if len(cells) == 2 and len(cells[0]) <= 60:
                key = cells[0].strip("*_ ")
                if not _junk_spec(key):
                    specs.setdefault(key, cells[1][:200])
        else:
            kv = KEY_VALUE_RE.match(line.strip().lstrip("-*• ").strip("*_ "))
            if kv:
                key, value = kv.group(1).strip(), kv.group(2).strip()
                if (
                    2 < len(key) <= 40
                    and value
                    and not value.startswith("http")
                    and not _junk_spec(key)
                ):
                    specs.setdefault(key, value[:200])
        if len(specs) >= 40:
            break
    return specs


def _markdown_description(markdown: str) -> str:
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", markdown):
        text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", block)  # drop links/images
        text = re.sub(r"[#>*_`|]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 120:
            blocks.append(text)
        if sum(len(b) for b in blocks) > 4000:
            break
    return " ".join(blocks)[:4000]


def _from_markdown(markdown: str, facts: PageFacts) -> bool:
    if not markdown:
        return False
    used = False
    prices = _markdown_prices(markdown)
    if prices:
        if facts.price.amount is None:
            facts.price, used = prices[0], True
        # A higher nearby price is the pre-discount one.
        if facts.price.amount is not None and facts.old_price is None:
            higher = [
                p for p in prices if p.amount and p.amount > facts.price.amount * 1.02
            ]
            if higher:
                facts.old_price = max(higher, key=lambda p: p.amount or 0)
                used = True

    if not facts.availability:
        low = markdown.lower()
        for pattern, label in AVAILABILITY_PATTERNS:
            if re.search(pattern, low):
                facts.availability, used = label, True
                break

    if not facts.sku:
        sku = SKU_LABEL_RE.search(markdown)
        if sku:
            facts.sku, used = sku.group(1)[:64], True

    if not facts.gtin:
        gtin = GTIN_LABEL_RE.search(markdown)
        if gtin and valid_gtin(gtin.group(1)):
            facts.gtin, used = gtin.group(1), True

    if not facts.specs:
        specs = _markdown_specs(markdown)
        if specs:
            facts.specs, used = specs, True

    if not facts.description:
        description = _markdown_description(markdown)
        if description:
            facts.description, used = description, True

    return used


def _gtin_from_images(image_urls: list[str]) -> str:
    # Shops often name gallery files after the EAN: 3337871316617_1.jpg
    for url in image_urls:
        for digits in DIGITS13_RE.findall(url):
            if valid_gtin(digits):
                return digits
    return ""


def _variant_hints(*texts: str) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for pattern in VARIANT_PATTERNS:
            for match in re.findall(pattern, text):
                token = re.sub(r"\s+", " ", match).strip()
                key = token.lower()
                if token and key not in seen:
                    seen.add(key)
                    hints.append(token)
    return hints[:12]


# --------------------------------------------------------------------- public


def extract_facts(
    *,
    url: str,
    markdown: str = "",
    metadata: dict[str, str] | None = None,
    structured_html: str = "",
    text: str = "",
    image_urls: list[str] | None = None,
) -> PageFacts:
    facts = PageFacts()
    sources: list[ExtractSource] = []
    metadata = {k: v for k, v in (metadata or {}).items() if isinstance(v, str)}
    body = markdown or text or ""

    nodes = parse_json_ld(structured_html)
    facts.jsonld_found = bool(nodes)
    if nodes and _from_json_ld(nodes, facts):
        sources.append("json-ld")
    if _from_microdata(structured_html, facts):
        sources.append("microdata")
    if _from_meta(metadata, facts):
        sources.append("meta")
    if _from_markdown(body, facts):
        sources.append("markdown")

    if not facts.gtin and image_urls:
        gtin = _gtin_from_images(image_urls)
        if gtin:
            facts.gtin = gtin
            sources.append("images")

    if not facts.breadcrumbs:
        crumbs = [
            c
            for c in re.split(r"\s*[/>»]\s*", (facts.title or "").split("|")[-1])
            if 2 < len(c) < 40
        ]
        if len(crumbs) > 1:
            facts.breadcrumbs = crumbs[:6]

    facts.variant_hints = _variant_hints(
        facts.title, " ".join(facts.specs.keys()), body[:2000]
    )
    facts.extracted_by = sources
    facts.completeness = facts_completeness(facts)
    return facts


def facts_completeness(facts: PageFacts) -> float:
    checks = (
        bool(facts.title),
        bool(facts.brand),
        facts.price.amount is not None,
        bool(facts.price.currency),
        bool(facts.availability),
        bool(facts.sku or facts.gtin),
        bool(facts.specs),
        len(facts.description) > 80,
    )
    return round(sum(checks) / len(checks), 3)


def classify_page(url: str, title: str = "", facts: PageFacts | None = None) -> str:
    low = url.lower()
    host = re.sub(r"^https?://(www\.)?", "", low).split("/")[0]
    path = (
        low[len(low.split("/")[0]) :]
        if "//" not in low
        else "/" + "/".join(low.split("/")[3:])
    )

    if any(h in host for h in VIDEO_HOSTS):
        return "video"
    if any(h in low for h in COMPARISON_HOSTS):
        return "price_comparison"
    if any(h in host for h in MARKETPLACE_HOSTS):
        return "marketplace"
    if any(h in path for h in ARTICLE_PATH_HINTS):
        return "article"

    has_price = bool(facts and facts.price.amount is not None)
    product_hint = any(h in path for h in PRODUCT_PATH_HINTS)
    category_hint = any(h in path for h in CATEGORY_PATH_HINTS)
    trailing_id = bool(re.search(r"[-/_](\d{3,9})(?:\.html?)?/?$", path))
    slug_depth = len([p for p in path.split("/") if p])

    if category_hint and not (has_price or trailing_id):
        return "category"
    if product_hint or trailing_id or has_price:
        return "product"
    if slug_depth >= 1 and re.search(r"[a-z]-[a-z]", path) and slug_depth <= 3:
        # A long hyphenated slug with no price is usually still a product page.
        return "product" if slug_depth <= 2 else "category"
    if slug_depth == 0:
        return "brand"
    return "unknown"
