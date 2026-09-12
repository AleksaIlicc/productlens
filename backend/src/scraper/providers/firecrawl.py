"""Firecrawl v2: broad search (the `site:rs` trick), image search, domain mapping
and page scraping. Every function returns its payload plus a ProviderCall so the
caller can show what was spent and what failed.
"""

import asyncio
import re

from scraper import cache
from scraper.http import post_json
from scraper.models import ImageRef, PageFacts, ProviderCall, ScrapedPage, SearchHit
from scraper.settings import get_scraper_settings
from scraper.urls import canonicalize, domain_of, region_of

SCRAPE_FORMATS = ["markdown", "links", "images"]

BLOCK_MARKERS = (
    "just a moment",
    "checking your browser",
    "enable javascript",
    "cf-browser-verification",
    "attention required",
    "access denied",
    "are you a robot",
    "unusual traffic",
    "captcha",
    "ddos protection",
    "request unsuccessful",
)

LD_JSON_BLOCK_RE = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>.*?</script>',
    re.S | re.I,
)
HEAD_RE = re.compile(r"<head[^>]*>(.*?)</head>", re.S | re.I)
ITEMPROP_WINDOW_RE = re.compile(
    r".{0,120}itemprop\s*=\s*[\"'][\w:]+[\"'].{0,220}", re.S | re.I
)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_scraper_settings().firecrawl_api_key}"}


def _url(path: str) -> str:
    return f"{get_scraper_settings().firecrawl_base_url.rstrip('/')}/{path.lstrip('/')}"


def credits_of(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("creditsUsed"), (int, float)):
        return float(payload["creditsUsed"])
    data = payload.get("data")
    if isinstance(data, dict):
        meta = data.get("metadata")
        if isinstance(meta, dict) and isinstance(meta.get("creditsUsed"), (int, float)):
            return float(meta["creditsUsed"])
    return None


def structured_digest(raw_html: str, *, max_chars: int = 200_000) -> str:
    """Keep only the parts of the HTML that carry structured data.

    lilly.rs ships 7.5 MB of rawHtml; storing that per page is pointless, but the
    JSON-LD / <head> / itemprop fragments are exactly what extract.py needs.
    """
    if not raw_html:
        return ""
    parts: list[str] = LD_JSON_BLOCK_RE.findall(raw_html)
    head = HEAD_RE.search(raw_html)
    if head:
        parts.append("<head>" + head.group(1)[:60_000] + "</head>")
    if "itemprop" in raw_html.lower():
        parts.extend(ITEMPROP_WINDOW_RE.findall(raw_html)[:80])
    digest = "\n".join(parts)
    return digest[:max_chars]


def _flatten_metadata(raw: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (raw or {}).items():
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value)
        if isinstance(value, bool) or isinstance(value, (int, float)):
            value = str(value)
        if not isinstance(value, str):
            continue
        if len(value) > 800:
            value = value[:800]
        out[str(key)] = value
    return out


def is_blocked(*, http_status: int | None, markdown: str) -> bool:
    if http_status is not None and (
        http_status in (401, 402, 403, 405, 406, 429) or http_status >= 500
    ):
        return True
    stripped = (markdown or "").strip()
    low = stripped.lower()
    if any(marker in low for marker in BLOCK_MARKERS) and len(stripped) < 6000:
        return True
    return len(stripped) < 200


async def _call(
    endpoint: str,
    body: dict,
    *,
    kind: str,
    query: str,
    use_cache: bool,
) -> tuple[dict | None, ProviderCall]:
    settings = get_scraper_settings()
    if not settings.firecrawl_api_key:
        return None, ProviderCall(
            provider="firecrawl",
            endpoint=endpoint,
            query=query,
            ok=False,
            error="FIRECRAWL_API_KEY nije postavljen",
        )

    cached = (
        cache.load(kind, body, settings.cache_ttl_hours)
        if (use_cache and settings.cache_enabled)
        else None
    )
    if cached is not None:
        return cached, ProviderCall(
            provider="firecrawl",
            endpoint=endpoint,
            query=query,
            ok=True,
            from_cache=True,
            elapsed_ms=0,
        )

    result = await post_json(
        _url(endpoint),
        body,
        _headers(),
        timeout=settings.http_timeout,
        attempts=settings.retry_attempts,
    )
    call = ProviderCall(
        provider="firecrawl",
        endpoint=endpoint,
        query=query,
        ok=result.ok,
        http_status=result.status,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
        credits_used=credits_of(result.json if isinstance(result.json, dict) else None),
    )
    if not result.ok or not isinstance(result.json, dict):
        return None, call
    return result.json, call


# ------------------------------------------------------------------- searching


async def search_web(
    query: str,
    *,
    limit: int = 10,
    location: str | None = None,
    use_cache: bool = True,
) -> tuple[list[SearchHit], ProviderCall]:
    body: dict = {"query": query, "limit": limit, "sources": ["web"]}
    if location:
        body["location"] = location
    payload, call = await _call(
        "search", body, kind="fc_search", query=query, use_cache=use_cache
    )
    hits: list[SearchHit] = []
    if payload:
        web = (payload.get("data") or {}).get("web") or []
        for index, item in enumerate(web):
            url = str(item.get("url") or "")
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    canonical_url=canonicalize(url),
                    domain=domain_of(url),
                    title=str(item.get("title") or "")[:300],
                    snippet=str(item.get("description") or "")[:600],
                    provider="firecrawl",
                    source_kind="search_web",
                    position=int(item.get("position") or index + 1),
                )
            )
    call.results = len(hits)
    return hits, call


async def search_images(
    query: str,
    *,
    limit: int = 10,
    use_cache: bool = True,
) -> tuple[list[SearchHit], ProviderCall]:
    """Image search doubles as page discovery: each image knows the page it sits on."""
    body = {"query": query, "limit": limit, "sources": ["images"]}
    payload, call = await _call(
        "search", body, kind="fc_images", query=query, use_cache=use_cache
    )
    hits: list[SearchHit] = []
    if payload:
        images = (payload.get("data") or {}).get("images") or []
        for index, item in enumerate(images):
            page_url = str(item.get("url") or "")
            image_url = str(item.get("imageUrl") or "")
            if not page_url or not image_url:
                continue
            hits.append(
                SearchHit(
                    url=page_url,
                    canonical_url=canonicalize(page_url),
                    domain=domain_of(page_url),
                    title=str(item.get("title") or "")[:300],
                    provider="firecrawl",
                    source_kind="search_images",
                    position=int(item.get("position") or index + 1),
                    images=[
                        ImageRef(
                            url=image_url,
                            role="search",
                            width=item.get("imageWidth"),
                            height=item.get("imageHeight"),
                            source="firecrawl:search_images",
                        )
                    ],
                )
            )
    call.results = len(hits)
    return hits, call


async def map_domain(
    domain_or_url: str,
    query: str,
    *,
    limit: int = 10,
    use_cache: bool = True,
) -> tuple[list[SearchHit], ProviderCall]:
    target = domain_or_url if "://" in domain_or_url else f"https://{domain_or_url}"
    body = {"url": target, "search": query, "limit": limit}
    payload, call = await _call(
        "map",
        body,
        kind="fc_map",
        query=f"{domain_or_url} :: {query}",
        use_cache=use_cache,
    )
    hits: list[SearchHit] = []
    if payload:
        for index, item in enumerate(payload.get("links") or []):
            url = str(item.get("url") if isinstance(item, dict) else item or "")
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    canonical_url=canonicalize(url),
                    domain=domain_of(url),
                    title=str(
                        (item.get("title") if isinstance(item, dict) else "") or ""
                    )[:300],
                    snippet=str(
                        (item.get("description") if isinstance(item, dict) else "")
                        or ""
                    )[:600],
                    provider="firecrawl",
                    source_kind="map",
                    position=index + 1,
                )
            )
    call.results = len(hits)
    return hits, call


# -------------------------------------------------------------------- scraping


async def scrape(
    url: str,
    *,
    timeout_ms: int | None = None,
    use_cache: bool = True,
    stealth: bool = False,
    max_markdown_chars: int | None = None,
    include_structured: bool = True,
    wait_for: int | None = None,
) -> tuple[ScrapedPage, ProviderCall, str]:
    """Scrape one page. Returns (page, call, structured_html_digest).

    The digest is deliberately NOT part of ScrapedPage: it is an extraction input,
    not something the UI or the LLM handoff should carry around.
    """
    settings = get_scraper_settings()
    formats = list(SCRAPE_FORMATS)
    if include_structured:
        formats.append("rawHtml")  # only source of JSON-LD; reduced to a digest below
    body: dict = {
        "url": url,
        "formats": formats,
        # False on purpose: main-content stripping drops price blocks and the
        # gallery on several .rs shops.
        "onlyMainContent": False,
        "timeout": timeout_ms or settings.scrape_timeout_ms,
    }
    if stealth:
        body["proxy"] = "stealth"
    if wait_for:
        # Angular/React shops (dm.rs) render price and gallery late.
        body["waitFor"] = wait_for

    page = ScrapedPage(
        canonical_url=canonicalize(url),
        url=url,
        domain=domain_of(url),
        region=region_of(url),  # type: ignore[arg-type]
        status="error",
        fetched_with="firecrawl",
        facts=PageFacts(),
    )

    use_disk = use_cache and settings.cache_enabled
    cached = (
        cache.load("fc_scrape", body, settings.cache_ttl_hours) if use_disk else None
    )
    if cached is not None:
        payload: dict | None = cached
        call = ProviderCall(
            provider="firecrawl", endpoint="scrape", query=url, ok=True, from_cache=True
        )
        page.from_cache = True
    else:
        result = await post_json(
            _url("scrape"),
            body,
            _headers(),
            timeout=settings.http_timeout,
            attempts=settings.retry_attempts,
        )
        call = ProviderCall(
            provider="firecrawl",
            endpoint="scrape",
            query=url,
            ok=result.ok,
            http_status=result.status,
            elapsed_ms=result.elapsed_ms,
            error=result.error,
            credits_used=credits_of(
                result.json if isinstance(result.json, dict) else None
            ),
        )
        payload = result.json if isinstance(result.json, dict) else None
        if payload is not None and isinstance(payload.get("data"), dict):
            data = payload["data"]
            # Never keep megabytes of HTML around: digest it immediately.
            data["rawHtml"] = structured_digest(str(data.get("rawHtml") or ""))
            if use_disk and result.ok:
                cache.store("fc_scrape", body, payload)
        if not result.ok:
            page.error = result.error or "Firecrawl scrape nije uspeo"
            page.http_status = result.status
            page.elapsed_ms = result.elapsed_ms
            return page, call, ""

    data = (payload or {}).get("data") or {}
    metadata = _flatten_metadata(data.get("metadata"))
    markdown = str(data.get("markdown") or "")
    structured = str(data.get("rawHtml") or "")
    cap = max_markdown_chars or settings.max_markdown_chars
    http_status = metadata.get("statusCode")

    page.metadata = metadata
    if str(http_status).isdigit():
        page.http_status = int(str(http_status))
    page.final_url = metadata.get("url") or metadata.get("sourceURL") or url
    page.truncated = len(markdown) > cap
    page.markdown = markdown[:cap]
    page.markdown_chars = len(markdown)
    page.elapsed_ms = call.elapsed_ms
    page.status = (
        "blocked"
        if is_blocked(http_status=page.http_status, markdown=markdown)
        else "ok"
    )

    images: list[ImageRef] = []
    for key in ("ogImage", "og:image", "twitter:image"):
        og = metadata.get(key)
        if og and og.startswith("http"):
            images.append(
                ImageRef(url=og, role="og", source=f"firecrawl:metadata.{key}")
            )
            break
    for raw in data.get("images") or []:
        if isinstance(raw, str):
            images.append(ImageRef(url=raw, role="gallery", source="firecrawl:scrape"))
        elif isinstance(raw, dict) and raw.get("url"):
            images.append(
                ImageRef(
                    url=str(raw["url"]),
                    role="gallery",
                    width=raw.get("width"),
                    height=raw.get("height"),
                    source="firecrawl:scrape",
                )
            )
    page.images = images
    return page, call, structured


async def scrape_many(
    urls: list[str],
    *,
    concurrency: int | None = None,
    **kwargs,
) -> tuple[list[tuple[ScrapedPage, str]], list[ProviderCall]]:
    """Scrape in parallel, bounded, input order preserved."""
    settings = get_scraper_settings()
    semaphore = asyncio.Semaphore(max(1, concurrency or settings.scrape_concurrency))

    async def one(url: str) -> tuple[ScrapedPage, ProviderCall, str]:
        async with semaphore:
            return await scrape(url, **kwargs)

    results = await asyncio.gather(*(one(u) for u in urls), return_exceptions=True)
    pages: list[tuple[ScrapedPage, str]] = []
    calls: list[ProviderCall] = []
    for url, result in zip(urls, results):
        if isinstance(result, BaseException):
            pages.append(
                (
                    ScrapedPage(
                        canonical_url=canonicalize(url),
                        url=url,
                        domain=domain_of(url),
                        region=region_of(url),  # type: ignore[arg-type]
                        status="error",
                        error=f"{type(result).__name__}: {result}"[:200],
                        fetched_with="firecrawl",
                    ),
                    "",
                )
            )
            calls.append(
                ProviderCall(
                    provider="firecrawl",
                    endpoint="scrape",
                    query=url,
                    ok=False,
                    error=str(result)[:200],
                )
            )
            continue
        page, call, structured = result
        pages.append((page, structured))
        calls.append(call)
    return pages, calls
