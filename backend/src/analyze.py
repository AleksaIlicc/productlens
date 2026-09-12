"""The end-to-end run the UI drives: search -> scrape -> read photos -> audit.

It is exposed as a job rather than one long request because the whole thing
takes minutes, and the browser is meant to show what is happening while it
runs. POST starts a job, GET returns everything reported since a cursor.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import jobs
from llm import compare_products, extract_image_facts
from products import Product
from schemas import CompareResponse, ImageFacts
from scraper import pipeline
from scraper.models import DiscoverRequest, DiscoverResponse, Scope, ScrapedOffer
from scraper.urls import region_of

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

# Wide enough to reach both a local and an international listing, small enough
# that a demo run stays under a minute of scraping.
SEARCH_DEFAULTS: dict = {
    "limit_candidates": 24,
    "scrape_top": 6,
    "providers": ["exa", "firecrawl"],
    "min_rs_pages": 2,
    "min_world_pages": 2,
    "include_image_search": True,
    "deep_domain_map": False,
}

# Raw page text is only a fallback when a page had no structured description.
MAX_FALLBACK_CHARS = 4000


class AnalyzeRequest(BaseModel):
    query: str
    scope: Scope = "both"
    use_cache: bool = True


class ComparePairRequest(BaseModel):
    a: Product
    b: Product


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
    pair: list[str] = Field(default_factory=list)
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


def _pick_pair(products: list[Product]) -> tuple[Product, Product] | None:
    """Best listing, then the best one from a different shop.

    A local and an international channel is the interesting pairing — that is
    where wording drifts — so prefer that split when it is available.
    """
    unique: list[Product] = []
    seen: set[str] = set()
    for product in products:
        if product.source in seen:
            continue
        seen.add(product.source)
        unique.append(product)

    if len(unique) < 2:
        return None
    first = unique[0]
    home = region_of(first.url)
    across = next((p for p in unique[1:] if region_of(p.url) != home), None)
    return first, across or unique[1]


def _analyzed(product: Product, facts: ImageFacts) -> Product:
    # Narrow images to what was actually analyzed, so the UI gallery matches.
    kept = [finding.image for finding in facts.per_image]
    return product.model_copy(update={"images": kept}) if kept else product


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


async def run_comparison(a: Product, b: Product, progress=_quiet) -> CompareResponse:
    """Read both galleries in parallel, then audit the two listings together."""
    facts_a, facts_b = await asyncio.gather(
        extract_image_facts(a, progress=progress),
        extract_image_facts(b, progress=progress),
    )
    return CompareResponse(
        a=_analyzed(a, facts_a),
        b=_analyzed(b, facts_b),
        image_facts_a=facts_a,
        image_facts_b=facts_b,
        comparison=await compare_products(a, b, facts_a, facts_b, progress),
    )


async def _analyze(job: jobs.Job, request: AnalyzeRequest) -> AnalyzeResult:
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
    result = AnalyzeResult(query=request.query, run=_stats(run), products=products)

    for warning in run.warnings:
        job.emit("scrape", warning, tone="warn")

    pair = _pick_pair(products)
    if pair is None:
        job.emit(
            "report",
            "Not enough listings to compare",
            detail="Fewer than two shops for this product could be read.",
            tone="warn",
        )
        return result

    a, b = pair
    result.pair = [a.id, b.id]
    job.emit(
        "vision",
        f"Comparing {a.source} with {b.source}",
        detail=f"{len(a.images)} + {len(b.images)} product photos to read",
        a=a.source,
        b=b.source,
    )
    result.comparison = await run_comparison(a, b, job.emit)
    job.emit("report", "Report ready", tone="ok")
    return result


async def _compare_only(job: jobs.Job, request: ComparePairRequest) -> AnalyzeResult:
    a, b = request.a, request.b
    job.emit(
        "vision",
        f"Comparing {a.source} with {b.source}",
        detail=f"{len(a.images)} + {len(b.images)} product photos to read",
        a=a.source,
        b=b.source,
    )
    comparison = await run_comparison(a, b, job.emit)
    job.emit("report", "Report ready", tone="ok")
    return AnalyzeResult(
        query=a.title, products=[a, b], pair=[a.id, b.id], comparison=comparison
    )


@router.post("")
async def start_analysis(request: AnalyzeRequest) -> JobStarted:
    query = request.query.strip()
    if not query:
        raise HTTPException(400, "Enter a product name")
    job = jobs.start(lambda j: _analyze(j, request.model_copy(update={"query": query})))
    return JobStarted(job_id=job.id)


@router.post("/compare")
async def start_comparison(request: ComparePairRequest) -> JobStarted:
    if request.a.id == request.b.id:
        raise HTTPException(400, "Pick two different listings")
    job = jobs.start(lambda j: _compare_only(j, request))
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
