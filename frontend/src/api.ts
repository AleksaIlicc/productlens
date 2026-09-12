export type Product = {
  id: string;
  source: string;
  url: string;
  title: string;
  raw_text: string;
  images: string[];
};

export type ImageFinding = {
  image: string;
  role: string;
  visible_text: string[];
  notes: string;
};

export type ImageFacts = {
  per_image: ImageFinding[];
  product_name: string;
  shade: string;
  volume: string;
  ingredients: string[];
  warnings: string[];
  claims: string[];
};

export type Status = 'match' | 'minor' | 'mismatch' | 'missing';
export type Severity = 'info' | 'low' | 'medium' | 'high';

// The fixed set of dimensions the backend audits (mirrors ComparisonField in
// schemas.py) — price/availability/SKU/category are intentionally out of scope.
export type ComparisonField =
  | 'product_identity'
  | 'shade'
  | 'volume'
  | 'ingredients'
  | 'warnings'
  | 'images_vs_text';

/** What one listing states for one dimension, keyed by its label (A, B, …). */
export type ListingValue = {
  listing: string;
  value: string;
};

export type FieldComparison = {
  field: ComparisonField;
  origin: 'web' | 'image' | 'both';
  values: ListingValue[];
  flagged: string[];
  status: Status;
  severity: Severity;
  explanation: string;
};

export type Comparison = {
  same_product: boolean;
  verdict: string;
  fields: FieldComparison[];
};

export type AnalysedListing = {
  label: string;
  product: Product;
  facts: ImageFacts;
};

export type CompareResponse = {
  listings: AnalysedListing[];
  comparison: Comparison;
};

// One run, stage by stage — the progress rail the run screen draws.
export type Stage =
  | 'search'
  | 'rank'
  | 'scrape'
  | 'vision'
  | 'audit'
  | 'report';

export type JobEvent = {
  seq: number;
  at_ms: number;
  stage: Stage;
  message: string;
  detail: string;
  tone: 'info' | 'ok' | 'warn';
  data: {
    // Running totals, sent by whichever stage learns them.
    shops?: number;
    candidates?: number;
    pages?: number;
    photos?: number;
    listings_count?: number;
    // One page, as it lands.
    domain?: string;
    url?: string;
    final_url?: string;
    region?: string;
    page_status?: string;
    from_cache?: boolean;
    // The listing a photo batch belongs to.
    source?: string;
    images?: string[];
    targets?: { domain: string; url: string }[];
    domains?: string[];
    queries?: string[];
    listings?: string[];
  };
};

export type RunStats = {
  run_id: string;
  elapsed_ms: number;
  candidates: number;
  scraped_ok: number;
  scraped_failed: number;
  images: number;
  queries_used: string[];
  warnings: string[];
};

export type AnalyzeResult = {
  query: string;
  run: RunStats | null;
  products: Product[];
  suggested: string[];
  comparison: CompareResponse | null;
};

export type JobState = {
  job_id: string;
  status: 'running' | 'done' | 'error';
  error: string;
  elapsed_ms: number;
  cursor: number;
  events: JobEvent[];
  result: AnalyzeResult | null;
};

// Every image is a remote URL from a live search result; route it through the
// scraper's proxy so shop hotlink-protection can't blank it out.
export const imageUrl = (url: string) =>
  `/api/scraper/image?url=${encodeURIComponent(url)}`;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

const post = <T>(url: string, body: unknown) =>
  request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const startSearch = (query: string) =>
  post<{ job_id: string }>('/api/analyze', { query });

export const startComparison = (listings: Product[]) =>
  post<{ job_id: string }>('/api/analyze/compare', { listings });

export const fetchJob = (jobId: string, cursor: number) =>
  request<JobState>(`/api/analyze/${jobId}?cursor=${cursor}`);
