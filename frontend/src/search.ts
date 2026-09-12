// Bridges the two otherwise-separate halves of the app: turns a scraper
// search result into the plain Product shape the comparison step consumes.

import type { Product } from './api';
import {
  type DiscoverRequest,
  discover,
  type ScrapedOffer,
} from './scraper/api';

const SEARCH_DEFAULTS: Omit<DiscoverRequest, 'query'> = {
  limit_candidates: 24,
  scrape_top: 6,
  providers: ['exa', 'firecrawl'],
  scope: 'both',
  min_rs_pages: 2,
  min_world_pages: 2,
  include_domains: [],
  exclude_domains: [],
  include_image_search: true,
  deep_domain_map: false,
  use_cache: true,
};

function offerText(offer: ScrapedOffer): string {
  const parts: string[] = [];
  if (offer.description) parts.push(offer.description);
  const specs = Object.entries(offer.specs);
  if (specs.length) {
    parts.push(
      `Specifikacija:\n${specs.map(([k, v]) => `${k}: ${v}`).join('\n')}`,
    );
  }
  if (!parts.length && offer.markdown)
    parts.push(offer.markdown.slice(0, 4000));
  return parts.join('\n\n');
}

export function offerToProduct(offer: ScrapedOffer): Product {
  return {
    id: offer.url,
    source: offer.domain,
    url: offer.url,
    title: offer.title || offer.domain,
    brand: offer.brand,
    raw_text: offerText(offer),
    images: offer.images,
  };
}

/** Search the web for a product name and return it pre-converted to Products. */
export async function searchProducts(query: string) {
  const run = await discover({ ...SEARCH_DEFAULTS, query });
  return { run, products: run.payload.offers.map(offerToProduct) };
}
