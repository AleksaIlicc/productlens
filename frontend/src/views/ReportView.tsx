import { useState } from 'react';
import type {
  AnalyzeResult,
  ComparisonField,
  FieldComparison,
  ImageFacts,
  Product,
  Severity,
} from '../api';
import {
  card,
  clock,
  Eyebrow,
  field as fieldClass,
  ghostButton,
  primaryButton,
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

function Finding({
  finding,
  a,
  b,
}: {
  finding: FieldComparison;
  a: string;
  b: string;
}) {
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

      <div className="mt-3.5 grid gap-2 sm:grid-cols-2">
        {[
          [a, finding.value_a],
          [b, finding.value_b],
        ].map(([source, value]) => (
          <div key={source} className="rounded border border-line bg-cream p-3">
            <p className="eyebrow truncate text-ink-50">{source}</p>
            <p className="mt-1.5 text-sm leading-snug text-ink">
              {value || '—'}
            </p>
          </div>
        ))}
      </div>

      <p className="mt-3.5 text-[13px] leading-relaxed text-ink-70">
        {finding.explanation}
      </p>
    </li>
  );
}

function ChannelCard({
  product,
  facts,
  label,
}: {
  product: Product;
  facts: ImageFacts;
  label: string;
}) {
  const read: [string, string][] = [
    ['Name', facts.product_name],
    ['Shade', facts.shade],
    ['Volume', facts.volume],
  ];
  return (
    <article className={`${card} overflow-hidden`}>
      <header className="border-b border-line p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-ink text-[11px] font-bold text-cream">
            {label}
          </span>
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
          What the model read from {facts.per_image.length} photos
        </summary>
        <div className="space-y-3 px-4 pb-4">
          {facts.ingredients.length > 0 && (
            <p className="text-[12px] leading-relaxed text-ink-70">
              <span className="font-semibold text-ink">Ingredients:</span>{' '}
              {facts.ingredients.join(' · ')}
            </p>
          )}
          {facts.warnings.length > 0 && (
            <p className="text-[12px] leading-relaxed text-ink-70">
              <span className="font-semibold text-ink">Warnings:</span>{' '}
              {facts.warnings.join(' · ')}
            </p>
          )}
          {facts.claims.length > 0 && (
            <p className="text-[12px] leading-relaxed text-ink-70">
              <span className="font-semibold text-ink">Claims:</span>{' '}
              {facts.claims.join(' · ')}
            </p>
          )}
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

function PairPicker({
  products,
  pair,
  onCompare,
}: {
  products: Product[];
  pair: [string, string];
  onCompare: (a: Product, b: Product) => void;
}) {
  const [ids, setIds] = useState<[string, string]>(pair);
  const pick = (id: string) => products.find((p) => p.id === id);
  const [a, b] = [pick(ids[0]), pick(ids[1])];
  const changed = ids[0] !== pair[0] || ids[1] !== pair[1];
  const same = ids[0] === ids[1];

  return (
    <div className={`${card} mt-6 flex flex-wrap items-end gap-3 p-4`}>
      {([0, 1] as const).map((slot) => (
        <label key={slot} className="min-w-[14rem] flex-1">
          <span className="eyebrow text-ink-50">
            {slot === 0 ? 'Channel A' : 'Channel B'}
          </span>
          <select
            value={ids[slot]}
            onChange={(e) => {
              const next: [string, string] = [...ids];
              next[slot] = e.target.value;
              setIds(next);
            }}
            className={`${fieldClass} mt-1.5`}
          >
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.source}
                {product.title ? ` — ${product.title}` : ''}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button
        type="button"
        disabled={same || !changed || !a || !b}
        onClick={() => a && b && onCompare(a, b)}
        className={ghostButton}
      >
        {same ? 'Pick two shops' : 'Compare this pair'}
      </button>
    </div>
  );
}

export default function ReportView({
  result,
  onCompare,
  onReset,
}: {
  result: AnalyzeResult;
  onCompare: (a: Product, b: Product) => void;
  onReset: () => void;
}) {
  const [showMatches, setShowMatches] = useState(false);
  const compared = result.comparison;

  if (!compared) {
    return (
      <div className="rise max-w-2xl">
        <Eyebrow>No report</Eyebrow>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-ink">
          Not enough listings to compare.
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-70">
          {result.products.length} readable listing
          {result.products.length === 1 ? '' : 's'} came back for “
          {result.query}”. A comparison needs two different shops — try a more
          specific product name, including the brand and the variant.
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

  const { a, b, image_facts_a, image_facts_b, comparison } = compared;
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
              : 'Both channels agree on every check.'}
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-70">
            {comparison.verdict}
          </p>
        </div>
        <button type="button" onClick={onReset} className={ghostButton}>
          New search
        </button>
      </div>

      <dl className="mt-7 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
        {[
          ['Compared', `${a.source} vs ${b.source}`],
          [
            'Same product',
            comparison.same_product ? 'Yes' : 'No — different item',
          ],
          ['High severity', `${high}`],
          [
            'Run time',
            result.run ? clock(result.run.elapsed_ms) : 'this session',
          ],
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

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-extrabold tracking-tight text-ink">
            Findings
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
              <Finding
                key={finding.field}
                finding={finding}
                a={a.source}
                b={b.source}
              />
            ))}
          </ul>
        ) : (
          <p
            className={`${card} mt-3 p-5 text-sm text-ink-70`}
          >{`Nothing was flagged across ${comparison.fields.length} dimensions. Tick the box above to see each one.`}</p>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-extrabold tracking-tight text-ink">
          Evidence
        </h2>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <ChannelCard product={a} facts={image_facts_a} label="A" />
          <ChannelCard product={b} facts={image_facts_b} label="B" />
        </div>
      </section>

      {result.products.length > 2 && (
        <section className="mt-10">
          <h2 className="text-lg font-extrabold tracking-tight text-ink">
            Compare another pair
          </h2>
          <p className="mt-1.5 text-[13px] text-ink-70">
            {result.products.length} listings came back from this search.
          </p>
          <PairPicker
            products={result.products}
            pair={[a.id, b.id]}
            onCompare={onCompare}
          />
        </section>
      )}

      {result.run && (
        <details className={`${card} mt-10 p-5`}>
          <summary className="cursor-pointer text-[13px] font-bold text-ink-70 hover:text-ink">
            Run details
          </summary>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ['Candidates', `${result.run.candidates}`],
              [
                'Pages scraped',
                `${result.run.scraped_ok} ok / ${result.run.scraped_failed} failed`,
              ],
              ['Photos found', `${result.run.images}`],
              ['Run id', result.run.run_id],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="eyebrow text-ink-50">{label}</dt>
                <dd className="mt-1 font-mono text-[12px] break-all text-ink">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {result.run.queries_used.length > 0 && (
            <div className="mt-4">
              <p className="eyebrow text-ink-50">Queries used</p>
              <p className="mt-1 font-mono text-[12px] text-ink-70">
                {result.run.queries_used.join('  ·  ')}
              </p>
            </div>
          )}
          {result.run.warnings.length > 0 && (
            <ul className="mt-4 space-y-1.5">
              {result.run.warnings.map((warning) => (
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
