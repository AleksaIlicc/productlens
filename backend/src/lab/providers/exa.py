"""Exa: precision search (a domain whitelist returns almost only real product
pages) plus /contents as a cheap fallback reader for pages Firecrawl cannot get.
"""

from lab import cache
from lab.http import post_json
from lab.models import ImageRef, ProviderCall, ScrapedPage, SearchHit
from lab.settings import get_lab_settings
from lab.urls import canonicalize, domain_of, region_of


def _headers() -> dict[str, str]:
    return {"x-api-key": get_lab_settings().exa_api_key}


def _url(path: str) -> str:
    return f"{get_lab_settings().exa_base_url.rstrip('/')}/{path.lstrip('/')}"


def _cost_of(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    cost = payload.get("costDollars")
    if isinstance(cost, dict) and isinstance(cost.get("total"), (int, float)):
        return float(cost["total"])
    return None


async def _call(
    endpoint: str,
    body: dict,
    *,
    kind: str,
    query: str,
    use_cache: bool,
) -> tuple[dict | None, ProviderCall]:
    settings = get_lab_settings()
    if not settings.exa_api_key:
        return None, ProviderCall(
            provider="exa",
            endpoint=endpoint,
            query=query,
            ok=False,
            error="EXA_API_KEY nije postavljen",
        )

    use_disk = use_cache and settings.lab_cache_enabled
    cached = cache.load(kind, body, settings.lab_cache_ttl_hours) if use_disk else None
    if cached is not None:
        return cached, ProviderCall(
            provider="exa", endpoint=endpoint, query=query, ok=True, from_cache=True
        )

    result = await post_json(
        _url(endpoint),
        body,
        _headers(),
        timeout=settings.lab_http_timeout,
        attempts=settings.lab_retry_attempts,
    )
    call = ProviderCall(
        provider="exa",
        endpoint=endpoint,
        query=query,
        ok=result.ok,
        http_status=result.status,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
        cost_usd=_cost_of(result.json if isinstance(result.json, dict) else None),
    )
    if not result.ok or not isinstance(result.json, dict):
        return None, call
    if use_disk:
        cache.store(kind, body, result.json)
    return result.json, call


def _images_of(item: dict, source: str) -> list[ImageRef]:
    images: list[ImageRef] = []
    main = item.get("image")
    if isinstance(main, str) and main.startswith("http"):
        images.append(ImageRef(url=main, role="main", source=source))
    extras = item.get("extras")
    if isinstance(extras, dict):
        for link in extras.get("imageLinks") or []:
            if isinstance(link, str) and link.startswith("http"):
                images.append(ImageRef(url=link, role="gallery", source=source))
    return images


async def search(
    query: str,
    *,
    num_results: int = 15,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    text_chars: int = 600,
    image_links: int = 8,
    search_type: str = "auto",
    use_cache: bool = True,
) -> tuple[list[SearchHit], ProviderCall]:
    body: dict = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
        "contents": {
            "text": {"maxCharacters": text_chars},
            "extras": {"imageLinks": image_links},
        },
    }
    # An empty list is not the same as "no filter" for Exa: omit the key.
    if include_domains:
        body["includeDomains"] = include_domains
    if exclude_domains:
        body["excludeDomains"] = exclude_domains

    payload, call = await _call(
        "search", body, kind="exa_search", query=query, use_cache=use_cache
    )
    hits: list[SearchHit] = []
    if payload:
        for index, item in enumerate(payload.get("results") or []):
            url = str(item.get("url") or "")
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    canonical_url=canonicalize(url),
                    domain=domain_of(url),
                    title=str(item.get("title") or "")[:300],
                    snippet=str(item.get("text") or "")[:400],
                    provider="exa",
                    source_kind="search_web",
                    position=index + 1,
                    text_preview=str(item.get("text") or "")[:1500],
                    images=_images_of(item, "exa:search"),
                )
            )
    call.results = len(hits)
    return hits, call


async def contents(
    urls: list[str],
    *,
    text_chars: int = 8000,
    image_links: int = 10,
    livecrawl: str = "preferred",
    use_cache: bool = True,
) -> tuple[list[ScrapedPage], ProviderCall]:
    """Fallback reader. Exa returns plain text (not markdown) — good enough for
    prices/descriptions when Firecrawl is blocked, and it costs ~$0.001.
    """
    if not urls:
        return [], ProviderCall(provider="exa", endpoint="contents", ok=True, results=0)

    body = {
        "urls": urls,
        "text": {"maxCharacters": text_chars},
        "extras": {"imageLinks": image_links},
        "livecrawl": livecrawl,
    }
    payload, call = await _call(
        "contents",
        body,
        kind="exa_contents",
        query=", ".join(urls)[:200],
        use_cache=use_cache,
    )

    pages: list[ScrapedPage] = []
    if payload:
        statuses = {
            str(s.get("id")): s
            for s in (payload.get("statuses") or [])
            if isinstance(s, dict)
        }
        for item in payload.get("results") or []:
            url = str(item.get("url") or item.get("id") or "")
            if not url:
                continue
            text = str(item.get("text") or "")
            status_entry = statuses.get(str(item.get("id") or url), {})
            state = str(status_entry.get("status") or "success").lower()
            page = ScrapedPage(
                canonical_url=canonicalize(url),
                url=url,
                final_url=url,
                domain=domain_of(url),
                region=region_of(url),  # type: ignore[arg-type]
                status="ok"
                if state == "success" and len(text.strip()) >= 200
                else "error",
                error="" if state == "success" else f"exa: {state}",
                fetched_with="exa",
                elapsed_ms=call.elapsed_ms,
                from_cache=call.from_cache,
                markdown=text,
                markdown_chars=len(text),
                metadata={
                    "exa_author": str(item.get("author") or ""),
                    "exa_source": str(status_entry.get("source") or ""),
                    "title": str(item.get("title") or ""),
                    "og:title": str(item.get("title") or ""),
                },
                images=_images_of(item, "exa:contents"),
            )
            pages.append(page)
        for missing in urls:
            if not any(
                p.url == missing or p.canonical_url == canonicalize(missing)
                for p in pages
            ):
                entry = statuses.get(missing, {})
                pages.append(
                    ScrapedPage(
                        canonical_url=canonicalize(missing),
                        url=missing,
                        domain=domain_of(missing),
                        region=region_of(missing),  # type: ignore[arg-type]
                        status="error",
                        error=f"exa: {entry.get('status', 'nema rezultata')}",
                        fetched_with="exa",
                    )
                )
    call.results = len([p for p in pages if p.status == "ok"])
    return pages, call


async def find_similar(
    url: str,
    *,
    num_results: int = 10,
    use_cache: bool = True,
) -> tuple[list[SearchHit], ProviderCall]:
    """Widen the candidate set from one known product page (same product elsewhere)."""
    body = {
        "url": url,
        "numResults": num_results,
        "excludeSourceDomain": False,
        "contents": {"text": {"maxCharacters": 300}, "extras": {"imageLinks": 5}},
    }
    payload, call = await _call(
        "findSimilar", body, kind="exa_similar", query=url, use_cache=use_cache
    )
    hits: list[SearchHit] = []
    if payload:
        for index, item in enumerate(payload.get("results") or []):
            hit_url = str(item.get("url") or "")
            if not hit_url:
                continue
            hits.append(
                SearchHit(
                    url=hit_url,
                    canonical_url=canonicalize(hit_url),
                    domain=domain_of(hit_url),
                    title=str(item.get("title") or "")[:300],
                    snippet=str(item.get("text") or "")[:400],
                    provider="exa",
                    source_kind="search_web",
                    position=index + 1,
                    images=_images_of(item, "exa:findSimilar"),
                )
            )
    call.results = len(hits)
    return hits, call
