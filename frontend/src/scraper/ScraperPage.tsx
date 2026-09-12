import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  type Candidate,
  type DiscoverRequest,
  type DiscoverResponse,
  discover,
  fetchHealth,
  fetchRun,
  fetchRuns,
  type PriceInfo,
  type Provider,
  type Region,
  type Scope,
  type ScrapedPage,
  scrapeOne,
} from './api';
import {
  Badge,
  Collapsible,
  card,
  copyToClipboard,
  downloadJson,
  Field,
  ImageGrid,
  RegionBadge,
  StatusBadge,
} from './parts';

const STORAGE_KEY = 'productlens.scraper.options.v1';

const DEFAULT_OPTIONS: DiscoverRequest = {
  query: '',
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

const SCOPE_LABEL: Record<Scope, string> = {
  both: 'Srbija + svet',
  rs: 'samo Srbija',
  world: 'samo svet',
};

const PAGE_TYPE_LABEL: Record<string, string> = {
  product: 'proizvod',
  category: 'kategorija',
  brand: 'brend',
  marketplace: 'marketplace',
  price_comparison: 'poređivač cena',
  article: 'članak',
  video: 'video',
  unknown: 'nepoznato',
};

function loadOptions(): DiscoverRequest {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_OPTIONS;
    return {
      ...DEFAULT_OPTIONS,
      ...(JSON.parse(raw) as Partial<DiscoverRequest>),
    };
  } catch {
    return DEFAULT_OPTIONS;
  }
}

const formatPrice = (price: PriceInfo) =>
  price.amount === null
    ? price.raw || ''
    : `${price.amount.toLocaleString('sr-RS')} ${price.currency || '?'}`;

const csv = (values: string[]) => values.join(', ');
const parseCsv = (value: string) =>
  value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

function Totals({ run }: { run: DiscoverResponse }) {
  const t = run.totals;
  const items: [string, string][] = [
    ['trajanje', `${(run.elapsed_ms / 1000).toFixed(1)} s`],
    ['kandidati', `${t.candidates}`],
    [
      'Srbija / region / svet',
      `${t.candidates_rs} / ${t.candidates_regional} / ${t.candidates_world}`,
    ],
    ['skrejpovano', `${t.scraped_ok} ok, ${t.scraped_failed} pad`],
    ['skrejp rs / svet', `${t.scraped_rs} / ${t.scraped_world}`],
    ['slike', `${t.images}`],
    ['Firecrawl krediti', `${t.firecrawl_credits}`],
    ['Exa trošak', `$${t.exa_cost_usd.toFixed(4)}`],
    ['iz keša', `${t.cache_hits}`],
  ];
  return (
    <div
      className={`${card} grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5`}
    >
      {items.map(([label, value]) => (
        <Field key={label} label={label} value={value} />
      ))}
      <Field
        label="run id"
        value={<code className="text-xs">{run.run_id}</code>}
      />
    </div>
  );
}

function ProviderCalls({ run }: { run: DiscoverResponse }) {
  return (
    <Collapsible title={`Pozivi provajdera (${run.provider_calls.length})`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[52rem] text-left text-xs">
          <thead className="text-slate-500 dark:text-slate-400">
            <tr>
              <th className="py-1 pr-3">provajder</th>
              <th className="py-1 pr-3">endpoint</th>
              <th className="py-1 pr-3">upit</th>
              <th className="py-1 pr-3">status</th>
              <th className="py-1 pr-3">ms</th>
              <th className="py-1 pr-3">rezultata</th>
              <th className="py-1 pr-3">cena</th>
            </tr>
          </thead>
          <tbody>
            {run.provider_calls.map((call) => (
              <tr
                key={`${call.provider}-${call.endpoint}-${call.query}-${call.elapsed_ms}-${call.results}`}
                className="border-t border-slate-100 dark:border-slate-800"
              >
                <td className="py-1 pr-3">{call.provider}</td>
                <td className="py-1 pr-3">{call.endpoint}</td>
                <td
                  className="max-w-[22rem] truncate py-1 pr-3"
                  title={call.query}
                >
                  {call.query}
                </td>
                <td className="py-1 pr-3">
                  {call.from_cache ? (
                    <Badge tone="blue">keš</Badge>
                  ) : call.ok ? (
                    <Badge tone="green">ok {call.http_status ?? ''}</Badge>
                  ) : (
                    <Badge tone="rose" title={call.error}>
                      greška {call.http_status ?? ''}
                    </Badge>
                  )}
                </td>
                <td className="py-1 pr-3">{call.elapsed_ms}</td>
                <td className="py-1 pr-3">{call.results}</td>
                <td className="py-1 pr-3">
                  {call.credits_used ? `${call.credits_used} kr` : ''}
                  {call.cost_usd ? `$${call.cost_usd.toFixed(4)}` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Collapsible>
  );
}

function CandidateTable({
  candidates,
  onScrape,
  scrapingUrl,
}: {
  candidates: Candidate[];
  onScrape: (url: string) => void;
  scrapingUrl: string | null;
}) {
  const [regionFilter, setRegionFilter] = useState<'all' | Region>('all');
  const shown = candidates.filter(
    (c) => regionFilter === 'all' || c.region === regionFilter,
  );
  const counts = {
    all: candidates.length,
    rs: candidates.filter((c) => c.region === 'rs').length,
    regional: candidates.filter((c) => c.region === 'regional').length,
    world: candidates.filter((c) => c.region === 'world').length,
  };
  const filters: ['all' | Region, string][] = [
    ['all', `sve (${counts.all})`],
    ['rs', `Srbija (${counts.rs})`],
    ['regional', `region (${counts.regional})`],
    ['world', `svet (${counts.world})`],
  ];

  return (
    <section className={`${card} p-4`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="mr-2 font-semibold">Pronađeni linkovi</h2>
        {filters.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setRegionFilter(value)}
            className={`rounded-md px-2 py-1 text-xs ${
              regionFilter === value
                ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[60rem] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <tr>
              <th className="py-1 pr-2">#</th>
              <th className="py-1 pr-2">skor</th>
              <th className="py-1 pr-2">region</th>
              <th className="py-1 pr-2">tip</th>
              <th className="py-1 pr-2">domen</th>
              <th className="py-1 pr-2">naslov</th>
              <th className="py-1 pr-2">izvor</th>
              <th className="py-1 pr-2" />
            </tr>
          </thead>
          <tbody>
            {shown.map((candidate, index) => (
              <tr
                key={candidate.canonical_url}
                className="border-t border-slate-100 align-top dark:border-slate-800"
              >
                <td className="py-2 pr-2 text-slate-400">{index + 1}</td>
                <td className="py-2 pr-2">
                  <span
                    className="cursor-help font-mono text-xs"
                    title={candidate.score_reasons.join('\n')}
                  >
                    {candidate.score.toFixed(2)}
                  </span>
                </td>
                <td className="py-2 pr-2">
                  <RegionBadge region={candidate.region} />
                </td>
                <td className="py-2 pr-2">
                  <Badge
                    tone={candidate.page_type === 'product' ? 'green' : 'slate'}
                  >
                    {PAGE_TYPE_LABEL[candidate.page_type] ??
                      candidate.page_type}
                  </Badge>
                </td>
                <td className="py-2 pr-2 whitespace-nowrap">
                  {candidate.domain}
                </td>
                <td className="max-w-[26rem] py-2 pr-2">
                  <a
                    href={candidate.url}
                    target="_blank"
                    rel="noreferrer"
                    className="line-clamp-2 text-sky-700 hover:underline dark:text-sky-400"
                  >
                    {candidate.title || candidate.url}
                  </a>
                  {candidate.images.length > 0 && (
                    <span className="mt-1 block text-xs text-slate-400">
                      {candidate.images.length} slika iz pretrage
                    </span>
                  )}
                </td>
                <td className="py-2 pr-2 text-xs text-slate-500 dark:text-slate-400">
                  {candidate.providers.join('+')}
                  {candidate.best_position
                    ? ` · #${candidate.best_position}`
                    : ''}
                </td>
                <td className="py-2 pr-2">
                  {candidate.scraped ? (
                    <Badge tone="green">skrejpovan</Badge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => onScrape(candidate.url)}
                      disabled={scrapingUrl === candidate.url}
                      className="rounded-md bg-slate-100 px-2 py-1 text-xs hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:hover:bg-slate-700"
                    >
                      {scrapingUrl === candidate.url
                        ? 'skrejpujem…'
                        : 'Skrejpuj'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!shown.length && (
        <p className="text-sm text-slate-500">Nema kandidata za ovaj filter.</p>
      )}
    </section>
  );
}

function PageCard({ page }: { page: ScrapedPage }) {
  const f = page.facts;
  return (
    <article className={`${card} space-y-3 p-4`}>
      <header className="flex flex-wrap items-center gap-2">
        <StatusBadge status={page.status} />
        <RegionBadge region={page.region} />
        <span className="font-semibold">{page.domain}</span>
        <Badge>{page.fetched_with ?? '—'}</Badge>
        {page.http_status !== null && <Badge>HTTP {page.http_status}</Badge>}
        <Badge>{page.elapsed_ms} ms</Badge>
        {page.from_cache && <Badge tone="blue">iz keša</Badge>}
        <Badge title="dužina markdown-a">{page.markdown_chars} znakova</Badge>
        {page.truncated && <Badge tone="amber">skraćeno</Badge>}
        <a
          href={page.final_url || page.url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-sm text-sky-700 hover:underline dark:text-sky-400"
        >
          otvori stranu ↗
        </a>
      </header>

      {page.error && (
        <p className="text-sm text-rose-700 dark:text-rose-400">{page.error}</p>
      )}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Field label="naslov" value={f.title} />
        <Field label="brend" value={f.brand} />
        <Field
          label="cena"
          value={
            <span>
              {formatPrice(f.price) || '—'}
              {f.old_price && (
                <span className="ml-2 text-slate-400 line-through">
                  {formatPrice(f.old_price)}
                </span>
              )}
            </span>
          }
        />
        <Field label="sirova cena" value={f.price.raw} />
        <Field label="dostupnost" value={f.availability} />
        <Field label="SKU" value={f.sku} />
        <Field label="GTIN / EAN" value={f.gtin} />
        <Field
          label="popunjenost"
          value={`${Math.round(f.completeness * 100)}%`}
        />
      </dl>

      <div className="flex flex-wrap gap-1">
        {f.variant_hints.map((hint) => (
          <Badge key={hint} tone="violet">
            {hint}
          </Badge>
        ))}
        {f.extracted_by.map((source) => (
          <Badge key={source} tone="blue">
            {source}
          </Badge>
        ))}
        {f.jsonld_found && <Badge tone="green">JSON-LD</Badge>}
      </div>

      {f.breadcrumbs.length > 0 && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {f.breadcrumbs.join(' › ')}
        </p>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium">
          Slike ({page.images.length})
        </h3>
        <ImageGrid images={page.images} />
      </div>

      {Object.keys(f.specs).length > 0 && (
        <Collapsible title={`Specifikacija (${Object.keys(f.specs).length})`}>
          <table className="w-full text-left text-sm">
            <tbody>
              {Object.entries(f.specs).map(([key, value]) => (
                <tr
                  key={key}
                  className="border-t border-slate-100 dark:border-slate-800"
                >
                  <th className="w-1/3 py-1 pr-3 font-normal text-slate-500 dark:text-slate-400">
                    {key}
                  </th>
                  <td className="py-1">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Collapsible>
      )}

      {f.description && (
        <Collapsible title="Opis">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            {f.description}
          </p>
        </Collapsible>
      )}

      <Collapsible title="Markdown sa strane">
        <pre className="max-h-80 overflow-auto rounded-lg bg-slate-50 p-3 text-xs whitespace-pre-wrap dark:bg-slate-950">
          {page.markdown || '(prazno)'}
        </pre>
      </Collapsible>

      <Collapsible title={`Metapodaci (${Object.keys(page.metadata).length})`}>
        <pre className="max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-950">
          {JSON.stringify(page.metadata, null, 2)}
        </pre>
      </Collapsible>
    </article>
  );
}

export default function ScraperPage() {
  const queryClient = useQueryClient();
  const [options, setOptions] = useState<DiscoverRequest>(loadOptions);
  const [run, setRun] = useState<DiscoverResponse | null>(null);
  const [manualPages, setManualPages] = useState<ScrapedPage[]>([]);
  const [scrapingUrl, setScrapingUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState('');

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(options));
    } catch {
      // private mode: not being able to remember options is not an error
    }
  }, [options]);

  const health = useQuery({
    queryKey: ['scraper', 'health'],
    queryFn: fetchHealth,
  });
  const runs = useQuery({ queryKey: ['scraper', 'runs'], queryFn: fetchRuns });

  const discovery = useMutation({
    mutationFn: discover,
    onSuccess: (data) => {
      setRun(data);
      setManualPages([]);
      queryClient.invalidateQueries({ queryKey: ['scraper', 'runs'] });
    },
  });

  const openRun = useMutation({
    mutationFn: fetchRun,
    onSuccess: (data) => {
      setRun(data);
      setManualPages([]);
      setOptions((prev) => ({ ...prev, query: data.query, scope: data.scope }));
    },
  });

  const manualScrape = useMutation({
    mutationFn: (url: string) => scrapeOne(url, options.use_cache),
    onMutate: (url) => setScrapingUrl(url),
    onSettled: () => setScrapingUrl(null),
    onSuccess: (page) =>
      setManualPages((prev) => [
        page,
        ...prev.filter((p) => p.url !== page.url),
      ]),
  });

  const busy = discovery.isPending || openRun.isPending;
  const error =
    discovery.error?.message ||
    openRun.error?.message ||
    manualScrape.error?.message;

  const pages = useMemo(
    () => [...manualPages, ...(run?.pages ?? [])],
    [manualPages, run],
  );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!options.query.trim()) return;
    discovery.mutate({ ...options, query: options.query.trim() });
  };

  const copyPayload = () => {
    if (!run) return;
    copyToClipboard(JSON.stringify(run.payload, null, 2))
      .then(() => setCopied('payload'))
      .catch(() => setCopied('greška'));
    setTimeout(() => setCopied(''), 2000);
  };

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 text-slate-900 dark:text-slate-100">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold">Scraper</h1>
        <Badge tone="amber">napredni prikaz</Badge>
        {health.data && (
          <>
            <Badge tone={health.data.firecrawl_key ? 'green' : 'rose'}>
              Firecrawl: {health.data.firecrawl_ping}
            </Badge>
            <Badge tone={health.data.exa_key ? 'green' : 'rose'}>
              Exa: {health.data.exa_ping}
            </Badge>
            <Badge tone={health.data.cache_enabled ? 'blue' : 'slate'}>
              keš: {health.data.cache_enabled ? 'uključen' : 'isključen'}
            </Badge>
          </>
        )}
        <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">
          samo pretraga + skrejpovanje, bez LLM obrade
        </span>
      </header>

      <form onSubmit={submit} className={`${card} space-y-3 p-4`}>
        <div className="flex flex-wrap gap-2">
          <input
            value={options.query}
            onChange={(e) => setOptions({ ...options, query: e.target.value })}
            placeholder="Vichy Dermablend Corrector 35 Sand"
            className="min-w-[18rem] flex-1 rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
          />
          <select
            value={options.scope}
            onChange={(e) =>
              setOptions({ ...options, scope: e.target.value as Scope })
            }
            className="rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
          >
            {(Object.keys(SCOPE_LABEL) as Scope[]).map((scope) => (
              <option key={scope} value={scope}>
                {SCOPE_LABEL[scope]}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={busy || !options.query.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
          >
            {discovery.isPending ? 'Tražim…' : 'Pretraži'}
          </button>
        </div>

        <Collapsible title="Napredno">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <label className="text-sm">
              strana za skrejp
              <input
                type="number"
                min={0}
                max={20}
                value={options.scrape_top}
                onChange={(e) =>
                  setOptions({ ...options, scrape_top: Number(e.target.value) })
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="text-sm">
              max kandidata
              <input
                type="number"
                min={1}
                max={100}
                value={options.limit_candidates}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    limit_candidates: Number(e.target.value),
                  })
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="text-sm">
              min. domaćih strana
              <input
                type="number"
                min={0}
                max={20}
                value={options.min_rs_pages}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    min_rs_pages: Number(e.target.value),
                  })
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="text-sm">
              min. svetskih strana
              <input
                type="number"
                min={0}
                max={20}
                value={options.min_world_pages}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    min_world_pages: Number(e.target.value),
                  })
                }
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="text-sm sm:col-span-2">
              samo domeni (odvoji zapetom)
              <input
                value={csv(options.include_domains)}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    include_domains: parseCsv(e.target.value),
                  })
                }
                placeholder="lilly.rs, notino.com"
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
            <label className="text-sm sm:col-span-2">
              izbaci domene
              <input
                value={csv(options.exclude_domains)}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    exclude_domains: parseCsv(e.target.value),
                  })
                }
                placeholder="amazon.com"
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-sm">
            {(['exa', 'firecrawl'] as Provider[]).map((provider) => (
              <label key={provider} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={options.providers.includes(provider)}
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      providers: e.target.checked
                        ? [...options.providers, provider]
                        : options.providers.filter((p) => p !== provider),
                    })
                  }
                />
                {provider}
              </label>
            ))}
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={options.include_image_search}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    include_image_search: e.target.checked,
                  })
                }
              />
              pretraga slika
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={options.deep_domain_map}
                onChange={(e) =>
                  setOptions({ ...options, deep_domain_map: e.target.checked })
                }
              />
              duboka pretraga po domenima (sporije)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={options.use_cache}
                onChange={(e) =>
                  setOptions({ ...options, use_cache: e.target.checked })
                }
              />
              koristi keš
            </label>
          </div>
        </Collapsible>
      </form>

      {error && (
        <p
          className={`${card} border-rose-300 p-3 text-sm text-rose-700 dark:border-rose-900 dark:text-rose-400`}
        >
          {error}
        </p>
      )}

      {discovery.isPending && (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Pretražujem Firecrawl i Exa, pa skrejpujem najbolje strane — traje
          15–60 s.
        </p>
      )}

      {!run && !discovery.isPending && (
        <p className={`${card} p-4 text-sm text-slate-500 dark:text-slate-400`}>
          Unesi naziv proizvoda (npr. „Vichy Dermablend Corrector 35 Sand“) i
          pokreni pretragu. Dobijaš sve linkove koje nađemo — domaće i svetske —
          sa cenama, podacima i slikama, plus JSON spreman za LLM korak.
        </p>
      )}

      {run && (
        <>
          <Totals run={run} />

          {run.warnings.length > 0 && (
            <ul
              className={`${card} space-y-1 p-4 text-sm text-amber-700 dark:text-amber-400`}
            >
              {run.warnings.map((warning) => (
                <li key={warning}>⚠ {warning}</li>
              ))}
            </ul>
          )}

          <div
            className={`${card} space-y-2 p-4 text-xs text-slate-500 dark:text-slate-400`}
          >
            <div>
              <span className="font-medium">upiti:</span>{' '}
              {run.queries_used.map((q) => (
                <code key={q} className="mr-2">
                  {q}
                </code>
              ))}
            </div>
            <ProviderCalls run={run} />
          </div>

          <CandidateTable
            candidates={run.candidates}
            onScrape={(url) => manualScrape.mutate(url)}
            scrapingUrl={scrapingUrl}
          />

          <section className="space-y-3">
            <h2 className="font-semibold">
              Skrejpovane strane ({pages.length})
            </h2>
            {pages.map((page) => (
              <PageCard
                key={`${page.canonical_url}-${page.fetched_with}`}
                page={page}
              />
            ))}
          </section>

          <section className={`${card} flex flex-wrap items-center gap-2 p-4`}>
            <button
              type="button"
              onClick={copyPayload}
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white dark:bg-slate-100 dark:text-slate-900"
            >
              {copied === 'payload' ? 'Kopirano ✓' : 'Kopiraj JSON za LLM'}
            </button>
            <button
              type="button"
              onClick={() =>
                downloadJson(`${run.run_id}-payload.json`, run.payload)
              }
              className="rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800"
            >
              Preuzmi payload
            </button>
            <button
              type="button"
              onClick={() =>
                downloadJson(`${run.run_id}-ceo-odgovor.json`, run)
              }
              className="rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800"
            >
              Preuzmi ceo odgovor
            </button>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              payload.offers = {run.payload.offers.length} ponuda za LLM korak
            </span>
          </section>

          <Collapsible title="Ceo JSON odgovor">
            <pre className={`${card} max-h-96 overflow-auto p-3 text-xs`}>
              {JSON.stringify(run, null, 2)}
            </pre>
          </Collapsible>
        </>
      )}

      <section className={`${card} p-4`}>
        <Collapsible title={`Prethodni runovi (${runs.data?.length ?? 0})`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-xs">
              <thead className="text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-1 pr-3">vreme</th>
                  <th className="py-1 pr-3">upit</th>
                  <th className="py-1 pr-3">opseg</th>
                  <th className="py-1 pr-3">kandidati</th>
                  <th className="py-1 pr-3">skrejpovano</th>
                  <th className="py-1 pr-3">slike</th>
                  <th className="py-1 pr-3" />
                </tr>
              </thead>
              <tbody>
                {(runs.data ?? []).map((summary) => (
                  <tr
                    key={summary.run_id}
                    className="border-t border-slate-100 dark:border-slate-800"
                  >
                    <td className="py-1 pr-3 whitespace-nowrap">
                      {summary.started_at}
                    </td>
                    <td className="max-w-[18rem] truncate py-1 pr-3">
                      {summary.query}
                    </td>
                    <td className="py-1 pr-3">{summary.scope}</td>
                    <td className="py-1 pr-3">{summary.candidates}</td>
                    <td className="py-1 pr-3">{summary.scraped_ok}</td>
                    <td className="py-1 pr-3">{summary.images}</td>
                    <td className="py-1 pr-3">
                      <button
                        type="button"
                        onClick={() => openRun.mutate(summary.run_id)}
                        className="rounded-md bg-slate-100 px-2 py-1 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
                      >
                        otvori
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      </section>
    </div>
  );
}
