"""The run the UI drives, in two halves.

Searching is fast enough to start on its own; auditing is not, and which
listings are worth auditing is the user's call. So `POST /api/analyze` finds
and scrapes, the user picks from what came back, and `POST /api/analyze/compare`
audits that selection. Both are jobs: they take minutes, and the browser is
meant to show what is happening while they run.
"""

import asyncio
import string

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import jobs
from llm import compare_listings, extract_image_facts
from products import Product
from schemas import AnalysedListing, Comparison, CompareResponse, ImageFacts
from scraper import pipeline
from scraper.models import DiscoverRequest, DiscoverResponse, Scope, ScrapedOffer
from scraper.urls import region_of

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

# Wide enough that every shop worth comparing shows up in the picker.
SEARCH_DEFAULTS: dict = {
    "limit_candidates": 24,
    "scrape_top": 10,
    "providers": ["exa", "firecrawl"],
    "min_rs_pages": 2,
    "min_world_pages": 2,
    "include_image_search": True,
    "deep_domain_map": False,
}

# Raw page text is only a fallback when a page had no structured description.
MAX_FALLBACK_CHARS = 4000

# The search never returns more than `scrape_top` listings, so this cap only
# has to match it — there is never a result the picker cannot select.
MAX_LISTINGS = SEARCH_DEFAULTS["scrape_top"]

# How many listings to tick for the user before they adjust the selection.
DEFAULT_SELECTION = 3


class AnalyzeRequest(BaseModel):
    query: str
    scope: Scope = "both"
    use_cache: bool = True


class CompareJobRequest(BaseModel):
    listings: list[Product]


class RunStats(BaseModel):
    run_id: str = ""
    elapsed_ms: int = 0
    candidates: int = 0
    scraped_ok: int = 0
    scraped_failed: int = 0
    images: int = 0
    queries_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalyzeResult(BaseModel):
    query: str = ""
    run: RunStats | None = None
    products: list[Product] = Field(default_factory=list)
    # Ids the picker should start with — a spread across shops and regions.
    suggested: list[str] = Field(default_factory=list)
    comparison: CompareResponse | None = None


class JobState(BaseModel):
    job_id: str
    status: jobs.JobStatus
    error: str
    elapsed_ms: int
    cursor: int
    events: list[jobs.JobEvent]
    result: AnalyzeResult | None


class JobStarted(BaseModel):
    job_id: str


def _offer_text(offer: ScrapedOffer) -> str:
    parts: list[str] = []
    if offer.variant_hints:
        parts.append("Variant stated on the page: " + ", ".join(offer.variant_hints))
    if offer.gtin:
        parts.append(f"GTIN/EAN: {offer.gtin}")
    if offer.description:
        parts.append(offer.description)
    if offer.specs:
        specs = "\n".join(f"{key}: {value}" for key, value in offer.specs.items())
        parts.append(f"Specification:\n{specs}")
    if not parts and offer.markdown:
        parts.append(offer.markdown[:MAX_FALLBACK_CHARS])
    return "\n\n".join(parts)


def _to_product(offer: ScrapedOffer) -> Product:
    return Product(
        id=offer.url,
        source=offer.domain,
        url=offer.url,
        title=offer.title or offer.domain,
        raw_text=_offer_text(offer),
        images=offer.images,
    )


def _worth_defaulting(product: Product) -> bool:
    # A page that barely rendered has nothing to audit; it stays in the picker,
    # it just should not be one of the listings ticked on arrival. Text length
    # is a poor test — some shops carry a one-line description and everything
    # else on the packaging — so this goes by photos and a specific title.
    return len(product.images) >= 3 and len(product.title) >= 25


def _suggest(products: list[Product], count: int = DEFAULT_SELECTION) -> list[str]:
    """A spread of shops to start the picker with, best first.

    One page per shop, and a change of region as early as possible — a local
    and an international channel is where the wording drifts.
    """
    by_shop: list[Product] = []
    seen: set[str] = set()
    for product in products:
        if product.source in seen:
            continue
        seen.add(product.source)
        by_shop.append(product)

    pool = [product for product in by_shop if _worth_defaulting(product)] or by_shop
    if len(pool) < 2:
        return [product.id for product in pool]

    picked = [pool[0]]
    home = region_of(pool[0].url)
    across = next((p for p in pool[1:] if region_of(p.url) != home), None)
    if across is not None:
        picked.append(across)
    for product in pool:
        if len(picked) >= count:
            break
        if product not in picked:
            picked.append(product)
    return [product.id for product in picked]


def _label(index: int) -> str:
    # A, B, C ... then AA, AB for the (capped) long tail.
    letters = string.ascii_uppercase
    if index < len(letters):
        return letters[index]
    return letters[index // len(letters) - 1] + letters[index % len(letters)]


def _analysed(product: Product, facts: ImageFacts, label: str) -> AnalysedListing:
    # Narrow images to what was actually analyzed, so the UI gallery matches.
    kept = [finding.image for finding in facts.per_image]
    return AnalysedListing(
        label=label,
        product=product.model_copy(update={"images": kept}) if kept else product,
        facts=facts,
    )


def _stats(run: DiscoverResponse) -> RunStats:
    return RunStats(
        run_id=run.run_id,
        elapsed_ms=run.elapsed_ms,
        candidates=run.totals.candidates,
        scraped_ok=run.totals.scraped_ok,
        scraped_failed=run.totals.scraped_failed,
        images=run.totals.images,
        queries_used=run.queries_used,
        warnings=run.warnings,
    )


def _quiet(stage: str, message: str, **_) -> None:
    return None


async def run_comparison(
    products: list[Product], progress=_quiet
) -> CompareResponse:
    """Read every gallery in parallel, then audit all listings together."""
    facts = await asyncio.gather(
        *(extract_image_facts(product, progress=progress) for product in products)
    )
    listings = [
        _analysed(product, fact, _label(index))
        for index, (product, fact) in enumerate(zip(products, facts))
    ]
    comparison: Comparison = await compare_listings(listings, progress)
    return CompareResponse(listings=listings, comparison=comparison)


async def _search(job: jobs.Job, request: AnalyzeRequest) -> AnalyzeResult:
    run = await pipeline.discover(
        DiscoverRequest(
            query=request.query,
            scope=request.scope,
            use_cache=request.use_cache,
            **SEARCH_DEFAULTS,
        ),
        job.emit,
    )
    products = [_to_product(offer) for offer in run.payload.offers]

    for warning in run.warnings:
        job.emit("scrape", warning, tone="warn")

    if len(products) < 2:
        job.emit(
            "report",
            "Not enough listings to compare",
            detail="Fewer than two shops for this product could be read.",
            tone="warn",
        )
    else:
        job.emit(
            "report",
            f"{len(products)} listings ready to compare",
            detail="pick the channels to audit",
            tone="ok",
        )
    return AnalyzeResult(
        query=request.query,
        run=_stats(run),
        products=products,
        suggested=_suggest(products),
    )


async def _compare(job: jobs.Job, request: CompareJobRequest) -> AnalyzeResult:
    products = request.listings
    job.emit(
        "vision",
        f"Auditing {len(products)} listings",
        detail=", ".join(product.source for product in products),
        listings=[product.source for product in products],
        listings_count=len(products),
    )
    comparison = await run_comparison(products, job.emit)
    job.emit("report", "Report ready", tone="ok")
    return AnalyzeResult(
        query=products[0].title, products=products, comparison=comparison
    )


@router.post("")
async def start_search(request: AnalyzeRequest) -> JobStarted:
    query = request.query.strip()
    if not query:
        raise HTTPException(400, "Enter a product name")
    job = jobs.start(lambda j: _search(j, request.model_copy(update={"query": query})))
    return JobStarted(job_id=job.id)


@router.post("/compare")
async def start_comparison(request: CompareJobRequest) -> JobStarted:
    listings = request.listings
    if len(listings) < 2:
        raise HTTPException(400, "Pick at least two listings to compare")
    if len(listings) > MAX_LISTINGS:
        raise HTTPException(400, f"Pick at most {MAX_LISTINGS} listings")
    if len({listing.id for listing in listings}) != len(listings):
        raise HTTPException(400, "The same listing was picked twice")
    job = jobs.start(lambda j: _compare(j, request))
    return JobStarted(job_id=job.id)


@router.get("/{job_id}")
async def job_state(job_id: str, cursor: int = Query(default=0, ge=0)) -> JobState:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "This run is no longer available")
    return JobState(
        job_id=job.id,
        status=job.status,
        error=job.error,
        elapsed_ms=job.elapsed_ms,
        cursor=len(job.events),
        events=job.since(cursor),
        result=job.result if job.status == "done" else None,
    )
