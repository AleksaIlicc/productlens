# Search + scraping side: no LLM calls here. `/discover` is what the main
# page's product search calls; these routes additionally expose the full run
# (candidates, scores, provider calls) for debugging.

import asyncio
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException, Query, Response

from scraper import cache, pipeline
from scraper.http import get_bytes, public_url_problem
from scraper.models import (
    DiscoverRequest,
    DiscoverResponse,
    RunSummary,
    ScrapedPage,
    ScrapeOneRequest,
    ScraperHealth,
)
from scraper.providers import exa, firecrawl
from scraper.settings import CACHE_DIR, get_scraper_settings

router = APIRouter(prefix="/api/scraper", tags=["scraper"])


@router.get("/health")
async def health(
    ping: bool = Query(default=False, description="Call the providers (spends credits)"),
) -> ScraperHealth:
    settings = get_scraper_settings()
    firecrawl_ping = "key set" if settings.firecrawl_api_key else "no key"
    exa_ping = "key set" if settings.exa_api_key else "no key"

    if ping:
        fc_task = firecrawl.search_web("test", limit=1, use_cache=True)
        exa_task = exa.search("test", num_results=1, use_cache=True)
        (_fc_hits, fc_call), (_exa_hits, exa_call) = await asyncio.gather(
            fc_task, exa_task
        )
        firecrawl_ping = "ok" if fc_call.ok else f"error: {fc_call.error}"[:120]
        exa_ping = "ok" if exa_call.ok else f"error: {exa_call.error}"[:120]

    return ScraperHealth(
        firecrawl_key=bool(settings.firecrawl_api_key),
        exa_key=bool(settings.exa_api_key),
        cache_enabled=settings.cache_enabled,
        cache_dir=str(CACHE_DIR),
        runs=cache.runs_count(),
        firecrawl_ping=firecrawl_ping,
        exa_ping=exa_ping,
    )


@router.post("/discover")
async def discover(request: DiscoverRequest) -> DiscoverResponse:
    if not request.query.strip():
        raise HTTPException(400, "Enter a product name")
    if not request.providers:
        raise HTTPException(400, "Pick at least one provider")
    return await pipeline.discover(request)


@router.post("/scrape")
async def scrape(request: ScrapeOneRequest) -> ScrapedPage:
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "The URL must start with http:// or https://")
    return await pipeline.scrape_one(request.model_copy(update={"url": url}))


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=200)) -> list[RunSummary]:
    return [RunSummary.model_validate(item) for item in cache.list_runs(limit)]


@router.get("/runs/{run_id}")
def run(run_id: str) -> DiscoverResponse:
    data = cache.load_run(run_id)
    if data is None:
        raise HTTPException(404, f"Unknown run: {run_id}")
    return DiscoverResponse.model_validate(data)


@router.get("/image")
async def image(url: str = Query(..., min_length=8, max_length=2048)) -> Response:
    # Proxied so shop hotlink protection can't blank out the gallery.
    target = unquote(url).strip()
    problem = await public_url_problem(target)
    if problem:
        raise HTTPException(400, f"Image not allowed: {problem}")

    settings = get_scraper_settings()
    status, body, content_type, error = await get_bytes(
        target,
        timeout=30.0,
        max_bytes=settings.max_image_bytes,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ProductLensScraper/0.1)",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": f"{urlsplit(target).scheme}://{urlsplit(target).netloc}/",
        },
        validate=public_url_problem,
    )
    if error:
        raise HTTPException(502, f"Image could not be fetched: {error}")
    if status is None or status >= 400 or not body:
        raise HTTPException(502, f"Image could not be fetched (HTTP {status})")
    if not content_type.startswith("image/"):
        raise HTTPException(
            415, f"Response is not an image ({content_type or 'unknown type'})"
        )

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
