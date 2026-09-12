import { useState } from 'react';
import type {
  AnalysedListing,
  CompareResponse,
  ComparisonField,
  FieldComparison,
  RunStats,
  Severity,
} from '../api';
import {
  card,
  clock,
  Eyebrow,
  ghostButton,
  SeverityTag,
  StatusChip,
  Thumb,
} from '../ui';

const FIELD_LABEL: Record<ComparisonField, string> = {
  product_identity: 'Product identity',
  shade: 'Shade',
  volume: 'Volume',
  ingredients: 'Ingredients (INCI)',
  warnings: 'Warnings',
  images_vs_text: 'Photos vs text',
};

const ORIGIN_LABEL = {
  web: 'from page text',
  image: 'from photos',
  both: 'page text + photos',
};

const SEVERITY_RANK: Record<Severity, number> = {
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
};

const STATUS_RANK = { mismatch: 3, missing: 2, minor: 1, match: 0 } as const;

const byImportance = (a: FieldComparison, b: FieldComparison) =>
  STATUS_RANK[b.status] - STATUS_RANK[a.status] ||
  SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity];

function LabelChip({ label, tone }: { label: string; tone: 'ink' | 'bad' }) {
  return (
    <span
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-bold ${
        tone === 'bad' ? 'bg-bad text-cream' : 'bg-ink text-cream'
      }`}
    >
      {label}
    </span>
  );
}

function Finding({
  finding,
  shops,
}: {
  finding: FieldComparison;
  shops: Map<string, string>;
}) {
  const flagged = new Set(finding.flagged);
  return (
    <li className="p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusChip status={finding.status} />
        <h3 className="text-[15px] font-bold text-ink">
          {FIELD_LABEL[finding.field]}
        </h3>
        <span className="text-[11px] text-ink-50">
          {ORIGIN_LABEL[finding.origin]}
        </span>
        <span className="ml-auto">
          <SeverityTag severity={finding.severity} />
        </span>
      </div>

      <ul className="mt-3.5 divide-y divide-line overflow-hidden rounded border border-line">
        {finding.values.map((value) => {
          const odd = flagged.has(value.listing);
          return (
            <li
              key={value.listing}
              className={`flex items-start gap-3 px-3 py-2.5 ${
                odd ? 'border-l-2 border-l-bad bg-bad-bg/50' : 'bg-cream'
              }`}
            >
              <LabelChip label={value.listing} tone={odd ? 'bad' : 'ink'} />
              <span className="w-32 shrink-0 truncate font-mono text-[11px] text-ink-50">
                {shops.get(value.listing) ?? ''}
              </span>
              <span className="min-w-0 flex-1 text-[13px] leading-snug text-ink">
                {value.value || '—'}
              </span>
              {odd && (
                <span className="shrink-0 text-[10px] font-bold tracking-wide text-bad uppercase">
                  issue
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <p className="mt-3.5 text-[13px] leading-relaxed text-ink-70">
        {finding.explanation}
      </p>
    </li>
  );
}

function ChannelCard({ listing }: { listing: AnalysedListing }) {
  const { product, facts, label } = listing;
  const read: [string, string][] = [
    ['Name', facts.product_name],
    ['Shade', facts.shade],
    ['Volume', facts.volume],
  ];
  return (
    <article className={`${card} overflow-hidden`}>
      <header className="border-b border-line p-4">
        <div className="flex items-center justify-between gap-3">
          <LabelChip label={label} tone="ink" />
          <a
            href={product.url}
            target="_blank"
            rel="noreferrer"
            className="truncate font-mono text-[11px] text-wine underline-offset-2 hover:underline"
          >
            {product.source}
          </a>
        </div>
        <h3 className="mt-2.5 text-sm leading-snug font-bold text-ink">
          {product.title}
        </h3>
      </header>

      {product.images.length > 0 && (
        <div className="flex gap-2 overflow-x-auto border-b border-line p-4">
          {product.images.map((url) => (
            <Thumb
              key={url}
              url={url}
              alt={product.title}
              className="h-16 w-16 shrink-0"
            />
          ))}
        </div>
      )}

      <dl className="grid grid-cols-3 gap-px bg-line">
        {read.map(([key, value]) => (
          <div key={key} className="bg-paper px-4 py-3">
            <dt className="eyebrow text-ink-50">{key}</dt>
            <dd className="mt-1 text-[13px] leading-snug font-medium text-ink">
              {value || '—'}
            </dd>
          </div>
        ))}
      </dl>

      <details className="border-t border-line">
        <summary className="cursor-pointer px-4 py-3 text-[13px] font-semibold text-ink-70 hover:text-ink">
          What the model read from {facts.per_image.length} photo
          {facts.per_image.length === 1 ? '' : 's'}
        </summary>
        <div className="space-y-3 px-4 pb-4">
          {(
            [
              ['Ingredients', facts.ingredients],
              ['Warnings', facts.warnings],
              ['Claims', facts.claims],
            ] as [string, string[]][]
          )
            .filter(([, values]) => values.length > 0)
            .map(([key, values]) => (
              <p key={key} className="text-[12px] leading-relaxed text-ink-70">
                <span className="font-semibold text-ink">{key}:</span>{' '}
                {values.join(' · ')}
              </p>
            ))}
          {facts.per_image.map((finding) => (
            <div key={finding.image} className="flex gap-3">
              <Thumb
                url={finding.image}
                alt={finding.role}
                className="h-12 w-12 shrink-0"
              />
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-ink">
                  {finding.role}
                </p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-ink-70">
                  {finding.notes}
                </p>
                {finding.visible_text.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] leading-relaxed break-words text-ink-50">
                    {finding.visible_text.join(' · ')}
                  </p>
                )}
              </div>
            </div>
          ))}
          {!facts.per_image.length && (
            <p className="text-[12px] text-ink-50">
              No photo from this listing could be read.
            </p>
          )}
        </div>
      </details>
    </article>
  );
}

export default function ReportView({
  query,
  result,
  stats,
  onChangeSelection,
  onReset,
}: {
  query: string;
  result: CompareResponse;
  stats: RunStats | null;
  onChangeSelection: () => void;
  onReset: () => void;
}) {
  const [showMatches, setShowMatches] = useState(false);
  const { listings, comparison } = result;
  const shops = new Map(
    listings.map((listing) => [listing.label, listing.product.source]),
  );

  const flagged = comparison.fields.filter((f) => f.status !== 'match');
  const high = flagged.filter((f) => f.severity === 'high').length;
  const shown = (showMatches ? comparison.fields : flagged)
    .slice()
    .sort(byImportance);

  return (
    <div className="rise">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <Eyebrow>Report</Eyebrow>
          <h1 className="mt-3 text-3xl leading-tight font-extrabold tracking-tight text-ink sm:text-4xl">
            {flagged.length
              ? `${flagged.length} of ${comparison.fields.length} checks flagged.`
              : 'Every channel agrees on every check.'}
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-70">
            {comparison.verdict}
          </p>
        </div>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={onChangeSelection}
            className={ghostButton}
          >
            Change selection
          </button>
          <button type="button" onClick={onReset} className={ghostButton}>
            New search
          </button>
        </div>
      </div>

      <dl className="mt-7 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
        {[
          ['Channels', `${listings.length}`],
          [
            'Same product',
            comparison.same_product ? 'Yes' : 'No — not all the same',
          ],
          ['High severity', `${high}`],
          ['Search time', stats ? clock(stats.elapsed_ms) : '—'],
        ].map(([label, value]) => (
          <div key={label} className="bg-paper px-4 py-3">
            <dt className="eyebrow text-ink-50">{label}</dt>
            <dd
              className={`mt-1 truncate text-[13px] font-bold ${
                label === 'Same product' && !comparison.same_product
                  ? 'text-bad'
                  : 'text-ink'
              }`}
              title={value}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-xs text-ink-50">
        “{query}” ·{' '}
        {listings.map((l) => `${l.label} ${l.product.source}`).join('  ·  ')}
      </p>

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-extrabold tracking-tight text-ink">
            Differences
          </h2>
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-70">
            <input
              type="checkbox"
              checked={showMatches}
              onChange={(e) => setShowMatches(e.target.checked)}
              className="accent-wine"
            />
            Show dimensions that match
          </label>
        </div>

        {shown.length ? (
          <ul className={`${card} mt-3 divide-y divide-line`}>
            {shown.map((finding) => (
              <Finding key={finding.field} finding={finding} shops={shops} />
            ))}
          </ul>
        ) : (
          <p className={`${card} mt-3 p-5 text-sm text-ink-70`}>
            Nothing differs across {listings.length} channels on any of the{' '}
            {comparison.fields.length} dimensions. Tick the box above to see
            each one.
          </p>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-extrabold tracking-tight text-ink">
          Evidence
        </h2>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          {listings.map((listing) => (
            <ChannelCard key={listing.product.id} listing={listing} />
          ))}
        </div>
      </section>

      {stats && (
        <details className={`${card} mt-10 p-5`}>
          <summary className="cursor-pointer text-[13px] font-bold text-ink-70 hover:text-ink">
            Run details
          </summary>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ['Candidates', `${stats.candidates}`],
              [
                'Pages scraped',
                `${stats.scraped_ok} ok / ${stats.scraped_failed} failed`,
              ],
              ['Photos found', `${stats.images}`],
              ['Run id', stats.run_id],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="eyebrow text-ink-50">{label}</dt>
                <dd className="mt-1 font-mono text-[12px] break-all text-ink">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {stats.queries_used.length > 0 && (
            <div className="mt-4">
              <p className="eyebrow text-ink-50">Queries used</p>
              <p className="mt-1 font-mono text-[12px] text-ink-70">
                {stats.queries_used.join('  ·  ')}
              </p>
            </div>
          )}
          {stats.warnings.length > 0 && (
            <ul className="mt-4 space-y-1.5">
              {stats.warnings.map((warning) => (
                <li key={warning} className="text-[12px] text-warn">
                  {warning}
                </li>
              ))}
            </ul>
          )}
        </details>
      )}
    </div>
  );
}
