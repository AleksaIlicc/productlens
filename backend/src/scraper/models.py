from typing import Literal

from pydantic import BaseModel, Field

Provider = Literal["exa", "firecrawl"]
SourceKind = Literal["search_web", "search_images", "map", "contents", "scrape"]
PageType = Literal[
    "product",
    "category",
    "brand",
    "marketplace",
    "price_comparison",
    "article",
    "video",
    "unknown",
]
Region = Literal["rs", "regional", "world"]
Scope = Literal["both", "rs", "world"]
ExtractSource = Literal["json-ld", "microdata", "meta", "markdown", "images"]


class ImageRef(BaseModel):
    url: str
    role: Literal["main", "gallery", "og", "search", "unknown"] = "unknown"
    width: int | None = None
    height: int | None = None
    source: str = ""


class PriceInfo(BaseModel):
    raw: str = ""
    amount: float | None = None
    currency: str = ""


class SearchHit(BaseModel):
    url: str
    canonical_url: str
    domain: str
    title: str = ""
    snippet: str = ""
    provider: Provider
    source_kind: SourceKind
    position: int | None = None
    text_preview: str = ""
    images: list[ImageRef] = Field(default_factory=list)


class Candidate(BaseModel):
    canonical_url: str
    url: str
    domain: str
    tld: str = ""
    region: Region = "world"
    title: str = ""
    snippet: str = ""
    providers: list[Provider] = Field(default_factory=list)
    source_kinds: list[SourceKind] = Field(default_factory=list)
    best_position: int | None = None
    page_type: PageType = "unknown"
    score: float = 0.0
    score_reasons: list[str] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    scraped: bool = False


class PageFacts(BaseModel):
    title: str = ""
    brand: str = ""
    price: PriceInfo = Field(default_factory=PriceInfo)
    old_price: PriceInfo | None = None
    availability: str = ""
    sku: str = ""
    gtin: str = ""
    breadcrumbs: list[str] = Field(default_factory=list)
    specs: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    variant_hints: list[str] = Field(default_factory=list)
    extracted_by: list[ExtractSource] = Field(default_factory=list)
    jsonld_found: bool = False
    completeness: float = 0.0


class ScrapedPage(BaseModel):
    canonical_url: str
    url: str
    final_url: str = ""
    domain: str
    region: Region = "world"
    status: Literal["ok", "blocked", "error"] = "ok"
    http_status: int | None = None
    error: str = ""
    fetched_with: Provider | None = None
    elapsed_ms: int = 0
    from_cache: bool = False
    markdown: str = ""
    markdown_chars: int = 0
    truncated: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    images: list[ImageRef] = Field(default_factory=list)
    facts: PageFacts = Field(default_factory=PageFacts)


class ProviderCall(BaseModel):
    provider: Provider
    endpoint: str
    query: str = ""
    ok: bool = True
    http_status: int | None = None
    elapsed_ms: int = 0
    results: int = 0
    credits_used: float | None = None
    cost_usd: float | None = None
    from_cache: bool = False
    error: str = ""


class ScrapedOffer(BaseModel):
    """One shop's offer: the handoff unit for the LLM comparison step.

    Deliberately narrow — this is what becomes a `Product` (see
    frontend/src/search.ts), not a dump of everything `extract.py` found.
    Price/availability/SKU/GTIN are still on `PageFacts` above for the
    debug view; they're commercial/store metadata, out of scope for brand
    consistency (see `ComparisonField` in backend/src/schemas.py).
    """

    url: str
    domain: str
    title: str = ""
    brand: str = ""
    images: list[str] = Field(default_factory=list)
    specs: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    markdown: str = ""


class ScraperPayload(BaseModel):
    product_query: str
    generated_at: str
    offers: list[ScrapedOffer] = Field(default_factory=list)


class RunTotals(BaseModel):
    hits_raw: int = 0
    candidates: int = 0
    candidates_rs: int = 0
    candidates_regional: int = 0
    candidates_world: int = 0
    scraped_ok: int = 0
    scraped_failed: int = 0
    scraped_rs: int = 0
    scraped_world: int = 0
    images: int = 0
    firecrawl_credits: float = 0.0
    exa_cost_usd: float = 0.0
    cache_hits: int = 0


class DiscoverRequest(BaseModel):
    query: str
    limit_candidates: int = Field(default=24, ge=1, le=100)
    scrape_top: int = Field(default=6, ge=0, le=20)
    providers: list[Provider] = Field(default_factory=lambda: ["exa", "firecrawl"])
    # "both" never filters by region; it only balances. "rs"/"world" narrow the run.
    scope: Scope = "both"
    min_rs_pages: int = Field(default=2, ge=0, le=20)
    min_world_pages: int = Field(default=2, ge=0, le=20)
    prefer_countries: list[str] = Field(default_factory=lambda: ["rs"])
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    include_image_search: bool = True
    deep_domain_map: bool = False
    use_cache: bool = True
    max_markdown_chars: int | None = Field(default=None, ge=500, le=200000)


class ScrapeOneRequest(BaseModel):
    url: str
    use_cache: bool = True
    provider: Provider = "firecrawl"


class DiscoverResponse(BaseModel):
    run_id: str
    query: str
    scope: Scope = "both"
    queries_used: list[str] = Field(default_factory=list)
    started_at: str = ""
    elapsed_ms: int = 0
    totals: RunTotals = Field(default_factory=RunTotals)
    provider_calls: list[ProviderCall] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    pages: list[ScrapedPage] = Field(default_factory=list)
    payload: ScraperPayload
    warnings: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    query: str
    scope: str = "both"
    started_at: str = ""
    elapsed_ms: int = 0
    candidates: int = 0
    scraped_ok: int = 0
    images: int = 0


class ScraperHealth(BaseModel):
    firecrawl_key: bool
    exa_key: bool
    cache_enabled: bool
    cache_dir: str
    runs: int
    firecrawl_ping: str
    exa_ping: str
