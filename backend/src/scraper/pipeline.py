"""The scraper run: build query variants -> search both worlds in parallel -> merge and
rank -> scrape the best pages -> extract facts and images -> hand back a payload
the LLM step can consume. No LLM calls here.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from scraper import cache, merge
from scraper.extract import extract_facts
from scraper.images import clean_gallery, gallery_urls
from scraper.models import (
    Candidate,
    DiscoverRequest,
    DiscoverResponse,
    ProviderCall,
    RunTotals,
    ScrapedOffer,
    ScrapedPage,
    ScrapeOneRequest,
    ScraperPayload,
    SearchHit,
)
from scraper.providers import exa, firecrawl
from scraper.settings import get_scraper_settings
from scraper.urls import canonicalize, domain_of

MAP_DOMAINS_LIMIT = 4
# Below this, with no images, a page almost certainly did not finish rendering.
THIN_MARKDOWN_CHARS = 2500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_id() -> str:
    # Sortable by name, so list_runs stays cheap.
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )


def build_queries(query: str, *, scope: str = "both") -> dict[str, list[str]]:
    """Query recipes per provider and per world.

    Firecrawl needs `site:rs` to surface Serbian shops at all; Exa does the same job
    through a domain whitelist. The plain query is what finds the international shops.
    """
    base = query.strip()
    local = [f"{base} site:rs", f"{base} cena kupovina"]
    world = [base, f"{base} buy online price"]

    plan: dict[str, list[str]] = {
        "firecrawl_web": [],
        "exa": [],
        "firecrawl_images": [],
    }
    if scope in ("both", "rs"):
        plan["firecrawl_web"].extend(local)
    if scope in ("both", "world"):
        plan["firecrawl_web"].extend(world)
    plan["exa"] = [base]
    plan["firecrawl_images"] = [base]
    return plan


def _flatten(results: list) -> tuple[list[SearchHit], list[ProviderCall]]:
    hits: list[SearchHit] = []
    calls: list[ProviderCall] = []
    for result in results:
        if isinstance(result, BaseException):
            calls.append(
                ProviderCall(
                    provider="firecrawl",
                    endpoint="unknown",
                    ok=False,
                    error=f"{type(result).__name__}: {result}"[:200],
                )
            )
            continue
        hit_list, call = result
        hits.extend(hit_list)
        calls.append(call)
    return hits, calls


async def _run_searches(
    req: DiscoverRequest,
) -> tuple[list[SearchHit], list[ProviderCall]]:
    settings = get_scraper_settings()
    plan = build_queries(req.query, scope=req.scope)
    semaphore = asyncio.Semaphore(max(1, settings.search_concurrency))
    per_provider = max(8, min(20, req.limit_candidates))

    async def guarded(coro):
        async with semaphore:
            return await coro

    tasks = []
    if "firecrawl" in req.providers:
        for query in plan["firecrawl_web"]:
            tasks.append(
                guarded(
                    firecrawl.search_web(
                        query, limit=per_provider, use_cache=req.use_cache
                    )
                )
            )
        if req.include_image_search:
            for query in plan["firecrawl_images"]:
                tasks.append(
                    guarded(
                        firecrawl.search_images(query, limit=8, use_cache=req.use_cache)
                    )
                )
    if "exa" in req.providers:
        for query in plan["exa"]:
            if req.scope in ("both", "rs"):
                tasks.append(
                    guarded(
                        exa.search(
                            f"{query} kupovina",
                            num_results=per_provider,
                            include_domains=list(
                                merge.SR_SHOP_DOMAINS + merge.REGIONAL_SHOP_DOMAINS
                            ),
                            use_cache=req.use_cache,
                        )
                    )
                )
            if req.scope in ("both", "world"):
                tasks.append(
                    guarded(
                        exa.search(
                            f"{query} buy",
                            num_results=per_provider,
                            include_domains=list(
                                merge.WORLD_SHOP_DOMAINS + merge.MARKETPLACE_DOMAINS
                            ),
                            use_cache=req.use_cache,
                        )
                    )
                )
            # Unrestricted pass: catches shops that are not on any of our lists.
            tasks.append(
                guarded(
                    exa.search(query, num_results=per_provider, use_cache=req.use_cache)
                )
            )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return _flatten(results)


async def _deep_map(
    req: DiscoverRequest, seen_domains: set[str]
) -> tuple[list[SearchHit], list[ProviderCall]]:
    """Map shop domains we have not seen yet: high recall, ~10s per domain."""
    pool: list[str] = []
    if req.scope in ("both", "rs"):
        pool.extend(merge.SR_SHOP_DOMAINS[:8])
    if req.scope in ("both", "world"):
        pool.extend(merge.WORLD_SHOP_DOMAINS[:8])
    targets = [d for d in pool if d not in seen_domains][:MAP_DOMAINS_LIMIT]
    if not targets:
        return [], []

    semaphore = asyncio.Semaphore(max(1, get_scraper_settings().search_concurrency))

    async def one(domain: str):
        async with semaphore:
            return await firecrawl.map_domain(
                domain, req.query, limit=5, use_cache=req.use_cache
            )

    return _flatten(
        await asyncio.gather(*(one(d) for d in targets), return_exceptions=True)
    )


def _finalize_page(
    page: ScrapedPage, structured_html: str, candidate: Candidate | None
) -> ScrapedPage:
    settings = get_scraper_settings()
    raw_images = list(page.images)
    if candidate:
        known = {img.url for img in raw_images}
        raw_images.extend(img for img in candidate.images if img.url not in known)

    # Facts first: their GTIN/SKU tells the gallery cleaner which photos belong to
    # THIS product, since shops mix in related-product carousels.
    facts = extract_facts(
        url=page.url,
        markdown=page.markdown,
        metadata=page.metadata,
        structured_html=structured_html,
        image_urls=[img.url for img in raw_images],
    )
    page.images = clean_gallery(
        raw_images,
        page_url=page.final_url or page.url,
        max_images=settings.max_images,
        prefer_token=facts.gtin,
        prefer_tokens=(facts.sku,),
    )
    page.facts = facts
    if not page.facts.title and candidate:
        page.facts.title = candidate.title
    return page


async def _scrape_pages(
    req: DiscoverRequest,
    picks: list[Candidate],
) -> tuple[list[ScrapedPage], list[ProviderCall]]:
    if not picks:
        return [], []

    by_url = {c.url: c for c in picks}
    scraped, calls = await firecrawl.scrape_many(
        [c.url for c in picks],
        use_cache=req.use_cache,
        max_markdown_chars=req.max_markdown_chars,
    )

    pages: list[ScrapedPage] = []
    structured_by_url: dict[str, str] = {}
    for page, structured in scraped:
        structured_by_url[page.url] = structured
        pages.append(page)

    # A page that rendered almost nothing gets one retry with a render delay.
    thin = [
        p.url
        for p in pages
        if p.status == "ok" and p.markdown_chars < THIN_MARKDOWN_CHARS and not p.images
    ]
    if thin:
        retried, retry_calls = await firecrawl.scrape_many(
            thin,
            use_cache=req.use_cache,
            max_markdown_chars=req.max_markdown_chars,
            wait_for=5000,
        )
        calls.extend(retry_calls)
        better = {
            page.url: (page, structured)
            for page, structured in retried
            if page.status == "ok"
        }
        for index, page in enumerate(pages):
            replacement = better.get(page.url)
            if replacement and replacement[0].markdown_chars > page.markdown_chars:
                pages[index] = replacement[0]
                structured_by_url[replacement[0].url] = replacement[1]

    # Cheap second chance for whatever Firecrawl could not read.
    failed = [p.url for p in pages if p.status != "ok"]
    if failed and "exa" in req.providers:
        fallback_pages, fallback_call = await exa.contents(
            failed, use_cache=req.use_cache
        )
        calls.append(fallback_call)
        recovered = {p.url: p for p in fallback_pages if p.status == "ok"}
        for index, page in enumerate(pages):
            replacement = recovered.get(page.url)
            if replacement is not None:
                replacement.region = page.region
                pages[index] = replacement
                structured_by_url[replacement.url] = ""

    finalized = [
        _finalize_page(page, structured_by_url.get(page.url, ""), by_url.get(page.url))
        for page in pages
    ]
    return finalized, calls


def _build_payload(
    query: str, candidates: list[Candidate], pages: list[ScrapedPage]
) -> ScraperPayload:
    order = {c.canonical_url: index for index, c in enumerate(candidates)}
    ok_pages = sorted(
        (p for p in pages if p.status == "ok"),
        key=lambda p: order.get(p.canonical_url, 999),
    )
    offers = [
        ScrapedOffer(
            url=page.final_url or page.url,
            domain=page.domain,
            title=page.facts.title,
            brand=page.facts.brand,
            images=gallery_urls(page.images, get_scraper_settings().max_images),
            specs=page.facts.specs,
            description=page.facts.description,
            markdown=page.markdown,
        )
        for page in ok_pages
    ]
    return ScraperPayload(product_query=query, generated_at=_now_iso(), offers=offers)


def _totals(
    hits: list[SearchHit],
    candidates: list[Candidate],
    pages: list[ScrapedPage],
    calls: list[ProviderCall],
) -> RunTotals:
    totals = RunTotals(hits_raw=len(hits), candidates=len(candidates))
    for candidate in candidates:
        if candidate.region == "rs":
            totals.candidates_rs += 1
        elif candidate.region == "regional":
            totals.candidates_regional += 1
        else:
            totals.candidates_world += 1
    for page in pages:
        if page.status == "ok":
            totals.scraped_ok += 1
            if page.region in ("rs", "regional"):
                totals.scraped_rs += 1
            else:
                totals.scraped_world += 1
        else:
            totals.scraped_failed += 1
        totals.images += len(page.images)
    for call in calls:
        if call.from_cache:
            totals.cache_hits += 1
            continue  # cached calls cost nothing
        totals.firecrawl_credits += call.credits_used or 0.0
        totals.exa_cost_usd += call.cost_usd or 0.0
    totals.firecrawl_credits = round(totals.firecrawl_credits, 2)
    totals.exa_cost_usd = round(totals.exa_cost_usd, 4)
    return totals


def _warnings(
    req: DiscoverRequest,
    candidates: list[Candidate],
    pages: list[ScrapedPage],
    totals: RunTotals,
) -> list[str]:
    settings = get_scraper_settings()
    warnings: list[str] = []
    if not settings.firecrawl_api_key:
        warnings.append(
            "FIRECRAWL_API_KEY nije postavljen — Firecrawl pozivi su preskočeni."
        )
    if not settings.exa_api_key:
        warnings.append("EXA_API_KEY nije postavljen — Exa pozivi su preskočeni.")
    if candidates and candidates[0].score < 4.0:
        warnings.append(
            "Rezultati slabo odgovaraju upitu — proveri naziv ili dodaj brend."
        )
    if not candidates:
        warnings.append(
            "Nijedan link nije pronađen. Proveri naziv ili skloni filtere domena."
        )
    if req.scope == "both" and candidates:
        if not totals.candidates_rs and not totals.candidates_regional:
            warnings.append(
                "Nema srpskih (.rs) rezultata za ovaj upit — prikazani su samo svetski."
            )
        if not totals.candidates_world:
            warnings.append(
                "Nema svetskih rezultata za ovaj upit — prikazani su samo domaći."
            )
        if totals.scraped_ok and not totals.scraped_world:
            warnings.append(
                "Skrejpovane su samo domaće strane; svetske nisu prošle skrejpovanje."
            )
        if totals.scraped_ok and not totals.scraped_rs:
            warnings.append(
                "Skrejpovane su samo svetske strane; domaće nisu prošle skrejpovanje."
            )
    if pages and totals.scraped_ok == 0:
        blocked = [p.domain for p in pages if p.status == "blocked"]
        warnings.append(
            "Nijedna strana nije skrejpovana"
            + (f" (blokirano: {', '.join(sorted(set(blocked)))})" if blocked else "")
        )
    missing_price = [
        p.domain for p in pages if p.status == "ok" and p.facts.price.amount is None
    ]
    if missing_price:
        warnings.append(
            "Cena nije prepoznata na: " + ", ".join(sorted(set(missing_price)))
        )
    no_images = [p.domain for p in pages if p.status == "ok" and not p.images]
    if no_images:
        warnings.append("Nema slika sa: " + ", ".join(sorted(set(no_images))))
    truncated = [p.domain for p in pages if p.truncated]
    if truncated:
        warnings.append("Markdown je skraćen za: " + ", ".join(sorted(set(truncated))))
    return warnings


async def discover(req: DiscoverRequest) -> DiscoverResponse:
    loop = asyncio.get_running_loop()
    started = loop.time()
    run_id, started_at = _run_id(), _now_iso()

    hits, calls = await _run_searches(req)
    if req.deep_domain_map:
        map_hits, map_calls = await _deep_map(req, {h.domain for h in hits})
        hits.extend(map_hits)
        calls.extend(map_calls)

    candidates = merge.merge_hits(
        hits,
        query=req.query,
        scope=req.scope,
        prefer_countries=req.prefer_countries,
        include_domains=req.include_domains,
        exclude_domains=req.exclude_domains,
    )[: req.limit_candidates]

    picks = merge.pick_to_scrape(
        candidates,
        n=req.scrape_top,
        min_rs=req.min_rs_pages,
        min_world=req.min_world_pages,
    )
    picked_keys = {c.canonical_url for c in picks}
    for candidate in candidates:
        candidate.scraped = candidate.canonical_url in picked_keys

    pages, scrape_calls = await _scrape_pages(req, picks)
    calls.extend(scrape_calls)

    totals = _totals(hits, candidates, pages, calls)
    queries = build_queries(req.query, scope=req.scope)
    response = DiscoverResponse(
        run_id=run_id,
        query=req.query,
        scope=req.scope,
        queries_used=sorted({q for group in queries.values() for q in group}),
        started_at=started_at,
        elapsed_ms=int((loop.time() - started) * 1000),
        totals=totals,
        provider_calls=calls,
        candidates=candidates,
        pages=pages,
        payload=_build_payload(req.query, candidates, pages),
        warnings=_warnings(req, candidates, pages, totals),
    )
    await asyncio.to_thread(cache.save_run, response.model_dump(mode="json"))
    return response


async def scrape_one(req: ScrapeOneRequest) -> ScrapedPage:
    url = req.url.strip()
    if req.provider == "exa":
        pages, _call = await exa.contents([url], use_cache=req.use_cache)
        page = (
            pages[0]
            if pages
            else ScrapedPage(
                canonical_url=canonicalize(url),
                url=url,
                domain=domain_of(url),
                status="error",
                error="nema rezultata",
            )
        )
        return _finalize_page(page, "", None)

    page, _call, structured = await firecrawl.scrape(url, use_cache=req.use_cache)
    if page.status != "ok":
        # One retry through the stealth proxy before falling back to Exa.
        retry, _retry_call, retry_structured = await firecrawl.scrape(
            url, use_cache=req.use_cache, stealth=True
        )
        if retry.status == "ok":
            page, structured = retry, retry_structured
        else:
            fallback, _fallback_call = await exa.contents(
                [url], use_cache=req.use_cache
            )
            if fallback and fallback[0].status == "ok":
                page, structured = fallback[0], ""
    return _finalize_page(page, structured, None)
