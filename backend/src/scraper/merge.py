# Dedupe search hits into ranked candidates. Domestic and international shops
# rank on equal footing; .rs only gets a small tie-break bonus, and the scrape
# selection enforces a per-region quota so neither side crowds the other out.

import re
import unicodedata

from scraper.extract import classify_page
from scraper.models import Candidate, Region, SearchHit
from scraper.urls import domain_of, region_of, tld_of

# Curated, easy to extend. Verified by live search/scrape probes.
SR_SHOP_DOMAINS = (
    "lilly.rs",
    "apotekajankovic.rs",
    "benu.rs",
    "drmax.rs",
    "eapoteka.rs",
    "apoteka-online.rs",
    "apotekaonline.rs",
    "oliva.rs",
    "onlinea.rs",
    "apotekasrbotrade.rs",
    "dm.rs",
    "maxi.rs",
    "shoppster.rs",
    "tehnomanija.rs",
    "gigatron.rs",
    "winwin.rs",
    "emmezeta.rs",
    "idea.rs",
    "apotekabeograd.rs",
    "farmalogist.rs",
    "supervital.rs",
    "ananas.rs",
)
REGIONAL_SHOP_DOMAINS = (
    "notino.hr",
    "notino.si",
    "ljekarnaonline.hr",
    "vichy.hr",
    "ceneje.si",
    "lekarna24ur.si",
    "apotekamo.me",
    "apotekemaxima.me",
    "bhapoteka.ba",
    "farmacia.mk",
)
WORLD_SHOP_DOMAINS = (
    "notino.com",
    "notino.de",
    "notino.pl",
    "notino.co.uk",
    "lookfantastic.com",
    "douglas.de",
    "douglas.com",
    "sephora.com",
    "sephora.fr",
    "escentual.com",
    "flaconi.de",
    "feelunique.com",
    "cocooncenter.com",
    "newpharma.be",
    "pharmacyonline.com",
    "boots.com",
    "dm.de",
    "rossmann.de",
    "shop-apotheke.com",
    "docmorris.de",
    "mediamarkt.de",
    "bol.com",
    "toolstation.com",
    "bauhaus.info",
    "ocado.com",
    "iherb.com",
    "lyskin.com",
    "thefrenchcosmeticsclub.com",
    "domzdrowia.pl",
    "benulekaren.sk",
)
MARKETPLACE_DOMAINS = (
    "amazon.com",
    "amazon.de",
    "amazon.co.uk",
    "amazon.it",
    "amazon.fr",
    "amazon.es",
    "ebay.com",
    "ebay.de",
    "allegro.pl",
    "aliexpress.com",
    "etsy.com",
    "kupujemprodajem.com",
    "limundo.com",
    "kupindo.com",
)
PRICE_COMPARISON_DOMAINS = (
    "ceneo.pl",
    "ceneje.si",
    "jeftinije.rs",
    "idealo.de",
    "pricerunner.com",
    "skroutz.gr",
    "cenoteka.rs",
    "google.com",
)
BRAND_DOMAINS = (
    "vichy.rs",
    "vichy.com",
    "vichy.hr",
    "vichy.co.uk",
    "loreal.com",
    "nivea.rs",
    "nivea.com",
    "bosch-professional.com",
    "barilla.com",
)
# Not shops, and never worth scraping for offer data.
NOISE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "pinterest.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "quora.com",
    "wikipedia.org",
    "blogspot.com",
    "wordpress.com",
    "medium.com",
    "forum.krstarica.com",
    "ana.rs",
)
# Known bot walls: keep them as candidates (the user wants the links) but do not
# waste scrape credits on them first.
HARD_TO_SCRAPE_DOMAINS = (
    "amazon.com",
    "amazon.de",
    "amazon.co.uk",
    "sephora.com",
    "sephora.fr",
    "ulta.com",
    "walmart.com",
    "boots.com",
    "douglas.de",
    "instagram.com",
    "facebook.com",
)

SOURCE_KIND_WEIGHT = {
    "search_web": 1.0,
    "map": 0.8,
    "contents": 0.4,
    "search_images": 0.3,
    "scrape": 0.0,
}
PAGE_TYPE_WEIGHT = {
    "product": 2.0,
    "marketplace": 0.8,
    "brand": 0.6,
    "price_comparison": 0.2,
    "unknown": 0.0,
    "category": -1.0,
    "article": -1.5,
    "video": -3.0,
}
STOPWORDS = {"za", "i", "sa", "na", "od", "the", "and", "with", "ml", "gr", "kom"}


def fold(text: str) -> str:
    # Diacritic-insensitive: "tečni" == "tecni", "Šifra" == "sifra".
    swapped = text.replace("đ", "dj").replace("Đ", "Dj").replace("ђ", "dj")
    decomposed = unicodedata.normalize("NFKD", swapped)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def tokens_of(text: str) -> set[str]:
    return {
        t
        for t in re.split(r"[^a-z0-9]+", fold(text))
        if len(t) > 1 and t not in STOPWORDS
    }


def _endswith_any(domain: str, candidates: tuple[str, ...]) -> bool:
    return any(domain == c or domain.endswith("." + c) for c in candidates)


def region_for(url: str) -> Region:
    domain = domain_of(url)
    if _endswith_any(domain, SR_SHOP_DOMAINS) or tld_of(url) == "rs":
        return "rs"
    if _endswith_any(domain, REGIONAL_SHOP_DOMAINS):
        return "regional"
    return region_of(url)  # type: ignore[return-value]


def is_noise(url: str) -> bool:
    return _endswith_any(domain_of(url), NOISE_DOMAINS)


def _refine_page_type(url: str, page_type: str) -> str:
    domain = domain_of(url)
    if _endswith_any(domain, PRICE_COMPARISON_DOMAINS):
        return "price_comparison"
    if _endswith_any(domain, MARKETPLACE_DOMAINS):
        return "marketplace"
    if _endswith_any(domain, BRAND_DOMAINS) and page_type not in ("product",):
        return "brand"
    return page_type


def merge_hits(
    hits: list[SearchHit],
    *,
    query: str,
    scope: str = "both",
    prefer_countries: list[str] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[Candidate]:
    prefer = {c.lower().lstrip(".") for c in (prefer_countries or [])}
    include = {d.lower().lstrip(".") for d in (include_domains or []) if d.strip()}
    exclude = {d.lower().lstrip(".") for d in (exclude_domains or []) if d.strip()}
    query_tokens = tokens_of(query)

    merged: dict[str, Candidate] = {}
    for hit in hits:
        key = hit.canonical_url
        if not key:
            continue
        domain = hit.domain or domain_of(hit.url)
        if is_noise(hit.url) or _endswith_any(domain, tuple(exclude)):
            continue
        if include and not _endswith_any(domain, tuple(include)):
            continue
        region = region_for(hit.url)
        if scope == "rs" and region == "world":
            continue
        if scope == "world" and region != "world":
            continue

        existing = merged.get(key)
        if existing is None:
            existing = Candidate(
                canonical_url=key,
                url=hit.url,
                domain=domain,
                tld=tld_of(hit.url),
                region=region,
                title=hit.title,
                snippet=hit.snippet or hit.text_preview[:400],
            )
            merged[key] = existing

        if hit.provider not in existing.providers:
            existing.providers.append(hit.provider)
        if hit.source_kind not in existing.source_kinds:
            existing.source_kinds.append(hit.source_kind)
        if hit.position is not None:
            existing.best_position = (
                hit.position
                if existing.best_position is None
                else min(existing.best_position, hit.position)
            )
        if len(hit.title) > len(existing.title):
            existing.title = hit.title
        if len(hit.snippet) > len(existing.snippet):
            existing.snippet = hit.snippet
        known = {img.url for img in existing.images}
        existing.images.extend(img for img in hit.images if img.url not in known)

    for candidate in merged.values():
        candidate.page_type = _refine_page_type(  # type: ignore[assignment]
            candidate.url, classify_page(candidate.url, candidate.title)
        )
        candidate.score, candidate.score_reasons = _score(
            candidate, query_tokens, prefer
        )

    return sorted(
        merged.values(), key=lambda c: (-c.score, c.best_position or 999, c.domain)
    )


def _score(
    candidate: Candidate, query_tokens: set[str], prefer: set[str]
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if len(candidate.providers) > 1:
        score += 2.0
        reasons.append("both providers +2.0")
    best_kind = max(
        (SOURCE_KIND_WEIGHT.get(k, 0.0) for k in candidate.source_kinds), default=0.0
    )
    if best_kind:
        score += best_kind
        reasons.append(f"source {'/'.join(candidate.source_kinds)} +{best_kind:.1f}")
    if candidate.best_position:
        bonus = max(0.0, 1.2 - 0.08 * (candidate.best_position - 1))
        if bonus:
            score += bonus
            reasons.append(f"rank {candidate.best_position} +{bonus:.2f}")

    type_bonus = PAGE_TYPE_WEIGHT.get(candidate.page_type, 0.0)
    if type_bonus:
        score += type_bonus
        reasons.append(f"page type {candidate.page_type} {type_bonus:+.1f}")

    domain = candidate.domain
    if _endswith_any(domain, SR_SHOP_DOMAINS):
        score += 1.0
        reasons.append("known .rs shop +1.0")
    elif _endswith_any(domain, WORLD_SHOP_DOMAINS):
        score += 1.0
        reasons.append("known international shop +1.0")
    elif _endswith_any(domain, REGIONAL_SHOP_DOMAINS):
        score += 0.6
        reasons.append("regional shop +0.6")

    overlap = len(query_tokens & tokens_of(f"{candidate.title} {candidate.url}"))
    if query_tokens:
        if overlap:
            bonus = min(2.5, 2.5 * overlap / len(query_tokens))
            score += bonus
            reasons.append(
                f"poklapanje naziva {overlap}/{len(query_tokens)} +{bonus:.2f}"
            )
        else:
            score -= 2.0
            reasons.append("no overlap with the query -2.0")

    if _endswith_any(domain, HARD_TO_SCRAPE_DOMAINS):
        score -= 0.8
        reasons.append("domain is hard to scrape -0.8")

    # Deliberately small: a preference, not a filter, so world results stay visible.
    if prefer and candidate.tld in prefer:
        score += 0.35
        reasons.append(f".{candidate.tld} preferred +0.35")

    return round(score, 3), reasons


def pick_to_scrape(
    candidates: list[Candidate],
    *,
    n: int,
    min_rs: int = 2,
    min_world: int = 2,
    max_per_domain: int = 2,
) -> list[Candidate]:
    # Top-n, but with domain diversity and a guaranteed share per region.
    if n <= 0:
        return []

    usable = [c for c in candidates if c.page_type not in ("video", "article")]
    if not usable:
        usable = list(candidates)

    per_domain: dict[str, int] = {}
    chosen: list[Candidate] = []
    chosen_keys: set[str] = set()

    def take(pool: list[Candidate], limit: int) -> None:
        for candidate in pool:
            if len(chosen) >= n or limit <= 0:
                return
            if candidate.canonical_url in chosen_keys:
                continue
            if per_domain.get(candidate.domain, 0) >= max_per_domain:
                continue
            chosen.append(candidate)
            chosen_keys.add(candidate.canonical_url)
            per_domain[candidate.domain] = per_domain.get(candidate.domain, 0) + 1
            limit -= 1

    domestic = [c for c in usable if c.region in ("rs", "regional")]
    world = [c for c in usable if c.region == "world"]
    products_first = sorted(usable, key=lambda c: (c.page_type != "product", -c.score))

    take([c for c in domestic if c.page_type == "product"] or domestic, min(min_rs, n))
    take(
        [c for c in world if c.page_type == "product"] or world,
        min(min_world, max(0, n - len(chosen))),
    )
    take(products_first, n - len(chosen))
    return chosen
