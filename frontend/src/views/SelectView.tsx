// Between the two halves of a run: everything the search found, and the
// choice of which channels get audited against each other.

import { useState } from 'react';
import type { Product, RunStats } from '../api';
import { card, clock, Eyebrow, ghostButton, primaryButton, Thumb } from '../ui';

// Mirrors MAX_LISTINGS / the minimum in backend/src/analyze.py.
const MAX_PICKS = 8;
const MIN_PICKS = 2;

function isLocal(url: string): boolean {
  try {
    return new URL(url).hostname.endsWith('.rs');
  } catch {
    return false;
  }
}

function ListingCard({
  product,
  picked,
  disabled,
  onToggle,
}: {
  product: Product;
  picked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={`${card} flex cursor-pointer gap-3.5 p-3.5 transition-colors ${
        picked ? 'border-wine bg-rose-pale/40' : 'hover:border-line-strong'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <input
        type="checkbox"
        checked={picked}
        disabled={disabled}
        onChange={onToggle}
        className="mt-0.5 h-4 w-4 shrink-0 accent-wine"
      />
      {product.images[0] ? (
        <Thumb
          url={product.images[0]}
          alt={product.title}
          className="h-14 w-14 shrink-0"
        />
      ) : (
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded border border-line bg-shell text-[10px] text-ink-50">
          no image
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-mono text-[12px] font-semibold text-wine">
            {product.source}
          </span>
          <span className="shrink-0 rounded border border-line bg-shell px-1.5 py-px text-[10px] font-semibold text-ink-70">
            {isLocal(product.url) ? 'local' : 'international'}
          </span>
        </span>
        <span className="mt-1 line-clamp-2 block text-[13px] leading-snug font-semibold text-ink">
          {product.title}
        </span>
        <span className="mt-1 block text-[11px] text-ink-50">
          {product.images.length} photo
          {product.images.length === 1 ? '' : 's'} ·{' '}
          {product.raw_text.length.toLocaleString('en-US')} characters of text
        </span>
      </span>
    </label>
  );
}

export default function SelectView({
  query,
  products,
  suggested,
  stats,
  onCompare,
  onReset,
}: {
  query: string;
  products: Product[];
  suggested: string[];
  stats: RunStats | null;
  onCompare: (listings: Product[]) => void;
  onReset: () => void;
}) {
  const [picked, setPicked] = useState<string[]>(() =>
    suggested.length
      ? suggested
      : products.slice(0, MIN_PICKS).map((p) => p.id),
  );

  const toggle = (id: string) =>
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id],
    );

  const selection = products.filter((product) => picked.includes(product.id));
  const full = picked.length >= MAX_PICKS;

  if (products.length < MIN_PICKS) {
    return (
      <div className="rise max-w-2xl">
        <Eyebrow>No comparison</Eyebrow>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-ink">
          Not enough listings to compare.
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-70">
          {products.length} readable listing
          {products.length === 1 ? '' : 's'} came back for “{query}”. An audit
          needs at least two channels — try a more specific product name,
          including the brand and the variant.
        </p>
        <button
          type="button"
          onClick={onReset}
          className={`${primaryButton} mt-6`}
        >
          New search
        </button>
      </div>
    );
  }

  return (
    <div className="rise pb-28">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <Eyebrow>Select channels</Eyebrow>
          <h1 className="mt-3 text-3xl leading-tight font-extrabold tracking-tight text-ink">
            {products.length} listings found for “{query}”.
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-70">
            Pick the channels to audit. Every selected listing is read and
            checked against all the others, and only what differs between them
            is reported.
          </p>
        </div>
        <button type="button" onClick={onReset} className={ghostButton}>
          New search
        </button>
      </div>

      {stats && (
        <p className="mt-4 text-xs text-ink-50">
          {stats.candidates} candidate pages ranked · {stats.scraped_ok} read
          {stats.scraped_failed > 0 && `, ${stats.scraped_failed} unreadable`} ·{' '}
          {stats.images} photos · {clock(stats.elapsed_ms)}
        </p>
      )}

      <div className="mt-7 grid gap-3 sm:grid-cols-2">
        {products.map((product) => (
          <ListingCard
            key={product.id}
            product={product}
            picked={picked.includes(product.id)}
            disabled={full && !picked.includes(product.id)}
            onToggle={() => toggle(product.id)}
          />
        ))}
      </div>

      {stats && stats.warnings.length > 0 && (
        <ul className="mt-6 space-y-1.5">
          {stats.warnings.map((warning) => (
            <li key={warning} className="text-[12px] text-warn">
              {warning}
            </li>
          ))}
        </ul>
      )}

      <div className="fixed inset-x-0 bottom-0 border-t border-line bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-3.5">
          <p className="text-[13px] text-ink-70">
            <span className="tnum font-bold text-ink">{picked.length}</span> of{' '}
            {products.length} selected
            <span className="text-ink-50">
              {' '}
              · {MIN_PICKS} to {MAX_PICKS} channels
            </span>
          </p>
          <button
            type="button"
            disabled={picked.length < MIN_PICKS}
            onClick={() => onCompare(selection)}
            className={primaryButton}
          >
            {picked.length < MIN_PICKS
              ? `Pick ${MIN_PICKS - picked.length} more`
              : `Compare ${picked.length} listings`}
          </button>
        </div>
      </div>
    </div>
  );
}
