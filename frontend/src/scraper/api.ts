// Types + fetch helpers for the scraper (/api/scraper).
// Deliberately separate from src/api.ts so the two halves of the app do not collide.

export type Provider = 'exa' | 'firecrawl';
export type Region = 'rs' | 'regional' | 'world';
export type Scope = 'both' | 'rs' | 'world';
export type PageType =
  | 'product'
  | 'category'
  | 'brand'
  | 'marketplace'
  | 'price_comparison'
  | 'article'
  | 'video'
  | 'unknown';
export type PageStatus = 'ok' | 'blocked' | 'error';

export type ImageRef = {
  url: string;
  role: 'main' | 'gallery' | 'og' | 'search' | 'unknown';
  width: number | null;
  height: number | null;
  source: string;
};

export type PriceInfo = {
  raw: string;
  amount: number | null;
  currency: string;
};

export type PageFacts = {
  title: string;
  brand: string;
  price: PriceInfo;
  old_price: PriceInfo | null;
  availability: string;
  sku: string;
  gtin: string;
  breadcrumbs: string[];
  specs: Record<string, string>;
  description: string;
  variant_hints: string[];
  extracted_by: string[];
  jsonld_found: boolean;
  completeness: number;
};

export type Candidate = {
  canonical_url: string;
  url: string;
  domain: string;
  tld: string;
  region: Region;
  title: string;
  snippet: string;
  providers: Provider[];
  source_kinds: string[];
  best_position: number | null;
  page_type: PageType;
  score: number;
  score_reasons: string[];
  images: ImageRef[];
  scraped: boolean;
};

export type ScrapedPage = {
  canonical_url: string;
  url: string;
  final_url: string;
  domain: string;
  region: Region;
  status: PageStatus;
  http_status: number | null;
  error: string;
  fetched_with: Provider | null;
  elapsed_ms: number;
  from_cache: boolean;
  markdown: string;
  markdown_chars: number;
  truncated: boolean;
  metadata: Record<string, string>;
  images: ImageRef[];
  facts: PageFacts;
};

export type ProviderCall = {
  provider: Provider;
  endpoint: string;
  query: string;
  ok: boolean;
  http_status: number | null;
  elapsed_ms: number;
  results: number;
  credits_used: number | null;
  cost_usd: number | null;
  from_cache: boolean;
  error: string;
};

// Deliberately narrow — this is what becomes a Product (see
// frontend/src/search.ts). Price/availability/SKU/GTIN are still on
// ScrapedPage.facts for the debug view below; they're commercial/store
// metadata, out of scope for brand consistency.
export type ScrapedOffer = {
  url: string;
  domain: string;
  title: string;
  images: string[];
  specs: Record<string, string>;
  description: string;
  markdown: string;
};

export type RunTotals = {
  hits_raw: number;
  candidates: number;
  candidates_rs: number;
  candidates_regional: number;
  candidates_world: number;
  scraped_ok: number;
  scraped_failed: number;
  scraped_rs: number;
  scraped_world: number;
  images: number;
  firecrawl_credits: number;
  exa_cost_usd: number;
  cache_hits: number;
};

export type DiscoverResponse = {
  run_id: string;
  query: string;
  scope: Scope;
  queries_used: string[];
  started_at: string;
  elapsed_ms: number;
  totals: RunTotals;
  provider_calls: ProviderCall[];
  candidates: Candidate[];
  pages: ScrapedPage[];
  payload: {
    product_query: string;
    generated_at: string;
    offers: ScrapedOffer[];
  };
  warnings: string[];
};

export type DiscoverRequest = {
  query: string;
  limit_candidates: number;
  scrape_top: number;
  providers: Provider[];
  scope: Scope;
  min_rs_pages: number;
  min_world_pages: number;
  include_domains: string[];
  exclude_domains: string[];
  include_image_search: boolean;
  deep_domain_map: boolean;
  use_cache: boolean;
};

export type RunSummary = {
  run_id: string;
  query: string;
  scope: string;
  started_at: string;
  elapsed_ms: number;
  candidates: number;
  scraped_ok: number;
  images: number;
};

export type ScraperHealth = {
  firecrawl_key: boolean;
  exa_key: boolean;
  cache_enabled: boolean;
  cache_dir: string;
  runs: number;
  firecrawl_ping: string;
  exa_ping: string;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(
      typeof detail === 'string' ? detail : `Zahtev nije uspeo (${res.status})`,
    );
  }
  return res.json();
}

// Product images go through the backend so hotlink protection can't blank them.
export const proxiedImage = (url: string) =>
  `/api/scraper/image?url=${encodeURIComponent(url)}`;

export const fetchHealth = () => request<ScraperHealth>('/api/scraper/health');

export const fetchRuns = () => request<RunSummary[]>('/api/scraper/runs');

export const fetchRun = (runId: string) =>
  request<DiscoverResponse>(`/api/scraper/runs/${encodeURIComponent(runId)}`);

export const discover = (body: DiscoverRequest) =>
  request<DiscoverResponse>('/api/scraper/discover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const scrapeOne = (url: string, useCache = true) =>
  request<ScrapedPage>('/api/scraper/scrape', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, use_cache: useCache, provider: 'firecrawl' }),
  });
