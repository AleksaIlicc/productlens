export type Product = {
  id: string;
  source: string;
  url: string;
  title: string;
  brand: string;
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
  brand: string;
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
  | 'brand'
  | 'shade'
  | 'volume'
  | 'ingredients'
  | 'warnings'
  | 'images_vs_text';

export type FieldComparison = {
  field: ComparisonField;
  origin: 'web' | 'image' | 'both';
  value_a: string;
  value_b: string;
  status: Status;
  severity: Severity;
  explanation: string;
};

export type Comparison = {
  same_product: boolean;
  verdict: string;
  fields: FieldComparison[];
};

export type CompareResponse = {
  a: Product;
  b: Product;
  image_facts_a: ImageFacts;
  image_facts_b: ImageFacts;
  comparison: Comparison;
};

// Every image is a remote URL from a live search result; route it through the
// scraper's proxy so shop hotlink-protection can't blank it out.
export const imageUrl = (url: string) =>
  `/api/scraper/image?url=${encodeURIComponent(url)}`;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Zahtev nije uspeo (${res.status})`);
  }
  return res.json();
}

// `a`/`b` are built client-side from a live search result — see
// offerToProduct in search.ts.
export const fetchComparison = (a: Product, b: Product) =>
  request<CompareResponse>('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ a, b }),
  });
