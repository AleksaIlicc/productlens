import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import {
  type ComparisonField,
  type FieldComparison,
  fetchComparison,
  type ImageFacts,
  imageUrl,
  type Product,
  type Status,
} from './api';
import { searchProducts } from './search';

const STATUS_LABEL: Record<Status, string> = {
  match: 'poklapa se',
  minor: 'sitna razlika',
  mismatch: 'neslaganje',
  missing: 'nedostaje',
};

const FIELD_LABEL: Record<ComparisonField, string> = {
  product_identity: 'identitet proizvoda',
  brand: 'brend',
  shade: 'nijansa',
  volume: 'zapremina',
  ingredients: 'sastojci (INCI)',
  warnings: 'upozorenja',
  images_vs_text: 'slike naspram teksta',
};

const STATUS_STYLE: Record<Status, string> = {
  match:
    'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  minor: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300',
  mismatch: 'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-300',
  missing:
    'bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-300',
};

const ORIGIN_LABEL = {
  web: 'sa sajta',
  image: 'sa slike',
  both: 'sajt + slika',
};

const card =
  'rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900';

function ProductCard({ product, label }: { product: Product; label: string }) {
  return (
    <article className={`${card} overflow-hidden`}>
      <header className="border-b border-slate-200 p-4 dark:border-slate-800">
        <div className="flex items-baseline justify-between gap-3">
          <span className="rounded bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white dark:bg-slate-100 dark:text-slate-900">
            {label}
          </span>
          <a
            href={product.url}
            target="_blank"
            rel="noreferrer"
            className="truncate text-sm text-sky-700 hover:underline dark:text-sky-400"
          >
            {product.source}
          </a>
        </div>
        <h2 className="mt-2 text-base font-semibold">{product.title}</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {product.brand}
        </p>
      </header>

      <div className="flex gap-2 overflow-x-auto p-4">
        {product.images.map((url) => (
          <img
            key={url}
            src={imageUrl(url)}
            alt={product.title}
            className="h-20 w-20 shrink-0 rounded-lg border border-slate-200 bg-white object-contain dark:border-slate-800"
          />
        ))}
      </div>

      <details className="border-t border-slate-200 dark:border-slate-800">
        <summary className="cursor-pointer p-4 text-sm font-medium">
          Sadržaj sa sajta
        </summary>
        <p className="whitespace-pre-line px-4 pb-4 text-sm text-slate-600 dark:text-slate-400">
          {product.raw_text}
        </p>
      </details>
    </article>
  );
}

function ComparisonCard({
  field,
  a,
  b,
}: {
  field: FieldComparison;
  a: string;
  b: string;
}) {
  return (
    <li className={`${card} p-4`}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[field.status]}`}
        >
          {STATUS_LABEL[field.status]}
        </span>
        <h3 className="font-semibold">{FIELD_LABEL[field.field]}</h3>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {ORIGIN_LABEL[field.origin]} · ozbiljnost: {field.severity}
        </span>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-950">
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400">
            {a}
          </div>
          <div className="mt-1">{field.value_a}</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-950">
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400">
            {b}
          </div>
          <div className="mt-1">{field.value_b}</div>
        </div>
      </div>

      <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
        {field.explanation}
      </p>
    </li>
  );
}

function ImageFactsPanel({
  product,
  facts,
}: {
  product: Product;
  facts: ImageFacts;
}) {
  const summary = [
    ['Naziv', facts.product_name],
    ['Brend', facts.brand],
    ['Nijansa', facts.shade],
    ['Zapremina', facts.volume],
    ['Sastojci', facts.ingredients.join(' · ')],
    ['Upozorenja', facts.warnings.join(' · ')],
  ];
  return (
    <div className={`${card} p-4`}>
      <h3 className="font-semibold">{product.source}</h3>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {summary.map(([key, value]) => (
          <div key={key} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-slate-500 dark:text-slate-400">{key}</dt>
            <dd>{value || '—'}</dd>
          </div>
        ))}
      </dl>
      {facts.per_image.map((finding) => (
        <details key={finding.image} className="mt-2 text-sm">
          <summary className="cursor-pointer">
            <img
              src={imageUrl(finding.image)}
              alt={finding.role}
              className="mr-2 inline-block h-10 w-10 rounded border border-slate-200 bg-white object-contain align-middle dark:border-slate-800"
            />
            {finding.role}
          </summary>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            {finding.notes}
          </p>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            <span className="font-medium">Tekst sa slike:</span>{' '}
            {finding.visible_text.join(' · ')}
          </p>
        </details>
      ))}
    </div>
  );
}

function App() {
  // Everything selectable comes from search results found so far this
  // session — there's no seed data, both dropdowns pick from this pool.
  const [pool, setPool] = useState<Product[]>([]);
  const [ids, setIds] = useState<[string, string] | null>(null);
  const [showMatches, setShowMatches] = useState(false);
  const [query, setQuery] = useState('');

  const comparison = useMutation({
    mutationFn: ([a, b]: [Product, Product]) => fetchComparison(a, b),
  });

  const search = useMutation({
    mutationFn: searchProducts,
    onSuccess: ({ products: found }) => {
      if (!found.length) return;
      setPool((prev) => {
        const merged = new Map(prev.map((p) => [p.id, p]));
        for (const p of found) merged.set(p.id, p);
        return [...merged.values()];
      });
      // First search that turns up at least two offers: pre-fill both
      // slots so a result is visible right away.
      setIds(
        (prev) =>
          prev ?? (found.length >= 2 ? [found[0].id, found[1].id] : prev),
      );
      comparison.reset();
    },
  });

  const pick = (id: string) => pool.find((p) => p.id === id);
  const [a, b] = ids ? [pick(ids[0]), pick(ids[1])] : [undefined, undefined];
  const result = comparison.data;
  const fields =
    result?.comparison.fields.filter(
      (f) => showMatches || f.status !== 'match',
    ) ?? [];
  const flagged =
    result?.comparison.fields.filter((f) => f.status !== 'match').length ?? 0;

  return (
    <main className="mx-auto max-w-6xl p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold">ProductLens</h1>
        <a
          href="/scraper"
          className="text-sm text-sky-700 hover:underline dark:text-sky-400"
        >
          napredni prikaz pretrage →
        </a>
      </div>
      <p className="mt-1 text-slate-600 dark:text-slate-400">
        Poređenje iste stavke na dve prodavnice — tekst sa sajta plus podaci
        pročitani sa fotografija, pa LLM traži neslaganja.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) search.mutate(query.trim());
        }}
        className="mt-6 flex flex-wrap gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Pretraži proizvod, npr. Fenty Beauty Pro Filt'r 220"
          className={`${card} min-w-[18rem] flex-1 px-3 py-2 text-sm`}
        />
        <button
          type="submit"
          disabled={search.isPending || !query.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          {search.isPending ? 'Tražim…' : 'Pretraži'}
        </button>
      </form>
      {search.isPending && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Tražim i skrejpujem najbolje strane — traje 15–60 s.
        </p>
      )}
      {search.error && (
        <p className="mt-2 text-sm text-rose-600">
          {(search.error as Error).message}
        </p>
      )}
      {search.data && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Pronađeno {search.data.products.length} ponuda (
          {search.data.run.totals.scraped_rs} domaćih /{' '}
          {search.data.run.totals.scraped_world} svetskih) — dodate u padajuće
          liste ispod.
        </p>
      )}

      {!ids && !search.isPending && (
        <p
          className={`${card} mt-4 p-4 text-sm text-slate-500 dark:text-slate-400`}
        >
          Pretraži proizvod da dobiješ ponude sa različitih sajtova za
          poređenje.
        </p>
      )}

      {ids && a && b && (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {([0, 1] as const).map((slot) => (
              <select
                key={slot}
                value={ids[slot]}
                onChange={(e) => {
                  const next: [string, string] = [...ids];
                  next[slot] = e.target.value;
                  setIds(next);
                  comparison.reset();
                }}
                className={`${card} px-3 py-2 text-sm`}
              >
                {pool.map((p) => (
                  <option key={p.id} value={p.id}>
                    {slot === 0 ? 'A' : 'B'}: {p.source}
                    {p.title ? ` — ${p.title}` : ''}
                  </option>
                ))}
              </select>
            ))}
            <button
              type="button"
              onClick={() => comparison.mutate([a, b])}
              disabled={comparison.isPending || ids[0] === ids[1]}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
            >
              {comparison.isPending ? 'Analiziram…' : 'Uporedi preko LLM-a'}
            </button>
            {ids[0] === ids[1] && (
              <span className="text-sm text-amber-600">
                Izaberi dve različite ponude.
              </span>
            )}
          </div>

          <section className="mt-6 grid gap-4 lg:grid-cols-2">
            <ProductCard product={a} label="A" />
            <ProductCard product={b} label="B" />
          </section>

          {comparison.error && (
            <p className="mt-6 text-rose-600">
              {(comparison.error as Error).message}
            </p>
          )}

          {result && (
            <section className="mt-8">
              <div className={`${card} p-4`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-semibold ${
                      result.comparison.same_product
                        ? STATUS_STYLE.match
                        : STATUS_STYLE.mismatch
                    }`}
                  >
                    {result.comparison.same_product
                      ? 'isti proizvod'
                      : 'različit proizvod'}
                  </span>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    {flagged} flagovanih polja od{' '}
                    {result.comparison.fields.length}
                  </span>
                </div>
                <p className="mt-2">{result.comparison.verdict}</p>
              </div>

              <div className="mt-6 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Razlike</h2>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={showMatches}
                    onChange={(e) => setShowMatches(e.target.checked)}
                  />
                  prikaži i polja koja se poklapaju
                </label>
              </div>

              <ul className="mt-3 grid gap-3">
                {fields.map((field) => (
                  <ComparisonCard
                    key={field.field}
                    field={field}
                    a={a.source}
                    b={b.source}
                  />
                ))}
              </ul>

              <h2 className="mt-8 text-lg font-semibold">
                Šta je model pročitao sa slika
              </h2>
              <div className="mt-3 grid gap-4 lg:grid-cols-2">
                <ImageFactsPanel product={a} facts={result.image_facts_a} />
                <ImageFactsPanel product={b} facts={result.image_facts_b} />
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

export default App;
