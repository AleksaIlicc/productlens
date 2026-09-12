// What the user watches while a run happens. Everything on this screen comes
// from real events the backend pushed — the only thing the browser invents is
// the clock between polls.

import { useEffect, useMemo, useRef } from 'react';
import type { JobEvent, Stage } from '../api';
import { clock, Eyebrow, ghostButton, Thumb } from '../ui';

const STAGES: { id: Stage; label: string; hint: string }[] = [
  { id: 'search', label: 'Search', hint: 'Sweeping both providers' },
  { id: 'rank', label: 'Rank', hint: 'Scoring candidate pages' },
  { id: 'scrape', label: 'Scrape', hint: 'Reading the product pages' },
  { id: 'vision', label: 'Photos', hint: 'Reading the packaging' },
  { id: 'audit', label: 'Audit', hint: 'Cross-checking six dimensions' },
  { id: 'report', label: 'Report', hint: 'Composing the findings' },
];

type Source = {
  domain: string;
  url: string;
  status: 'pending' | 'ok' | 'failed';
  detail: string;
};

type Digest = {
  active: number;
  counters: { label: string; value: number }[];
  sources: Source[];
  photos: { url: string; source: string }[];
};

/** Fold the event stream into the shapes this screen draws. */
function digest(events: JobEvent[]): Digest {
  const counters = { shops: 0, candidates: 0, pages: 0, photos: 0 };
  const sources = new Map<string, Source>();
  const photos = new Map<string, string>();
  let active = 0;

  for (const event of events) {
    const index = STAGES.findIndex((stage) => stage.id === event.stage);
    if (index > active) active = index;
    const data = event.data;

    if (typeof data.shops === 'number') counters.shops = data.shops;
    if (typeof data.candidates === 'number')
      counters.candidates = data.candidates;
    if (typeof data.pages === 'number') counters.pages = data.pages;
    if (typeof data.photos === 'number') counters.photos = data.photos;

    // Keyed by URL, not domain: one shop can contribute two product pages.
    for (const target of data.targets ?? []) {
      sources.set(target.url, {
        domain: target.domain,
        url: target.url,
        status: 'pending',
        detail: '',
      });
    }
    if (data.url && data.page_status) {
      sources.set(data.url, {
        domain: data.domain ?? data.url,
        url: data.final_url ?? data.url,
        status: data.page_status === 'ok' ? 'ok' : 'failed',
        detail: event.detail,
      });
    }
    for (const image of data.images ?? []) {
      if (!photos.has(image)) photos.set(image, data.source ?? '');
    }
  }

  return {
    active,
    counters: [
      { label: 'Shops seen', value: counters.shops },
      { label: 'Candidates', value: counters.candidates },
      { label: 'Pages read', value: counters.pages },
      { label: 'Photos found', value: counters.photos },
    ],
    sources: [...sources.values()],
    photos: [...photos].map(([url, source]) => ({ url, source })),
  };
}

const SOURCE_STYLE: Record<Source['status'], string> = {
  pending: 'border-line-strong bg-shell text-ink-70',
  ok: 'border-ok-line bg-ok-bg text-ok',
  failed: 'border-warn-line bg-warn-bg text-warn',
};

const TONE_STYLE: Record<JobEvent['tone'], string> = {
  info: 'text-ink',
  ok: 'text-ok',
  warn: 'text-warn',
};

function StageRail({ active }: { active: number }) {
  return (
    <ol className="relative">
      {STAGES.map((stage, index) => {
        const state =
          index < active ? 'done' : index === active ? 'active' : 'todo';
        return (
          <li key={stage.id} className="relative flex gap-3.5 pb-6 last:pb-0">
            {index < STAGES.length - 1 && (
              <span
                aria-hidden="true"
                className={`absolute top-4 left-[7px] h-full w-px ${
                  state === 'done' ? 'bg-wine' : 'bg-line'
                }`}
              />
            )}
            <span
              className={`relative mt-1 h-[15px] w-[15px] shrink-0 rounded-full border-2 ${
                state === 'done'
                  ? 'border-wine bg-wine'
                  : state === 'active'
                    ? 'halo border-rose bg-paper'
                    : 'border-line-strong bg-paper'
              }`}
            />
            <div className="min-w-0">
              <p
                className={`text-sm leading-none font-bold ${
                  state === 'todo' ? 'text-ink-50' : 'text-ink'
                }`}
              >
                {stage.label}
              </p>
              <p
                className={`mt-1.5 text-xs leading-snug ${
                  state === 'active' ? 'text-rose' : 'text-ink-50'
                }`}
              >
                {state === 'done' ? 'Done' : stage.hint}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function RunView({
  query,
  events,
  elapsedMs,
  onCancel,
}: {
  query: string;
  events: JobEvent[];
  elapsedMs: number;
  onCancel: () => void;
}) {
  const { active, counters, sources, photos } = useMemo(
    () => digest(events),
    [events],
  );
  const log = useRef<HTMLDivElement>(null);

  // Keep the newest line in view without yanking the whole page around.
  useEffect(() => {
    const element = log.current;
    if (!element || !events.length) return;
    element.scrollTop = element.scrollHeight;
  }, [events]);

  const reading = STAGES[active].id === 'vision';

  return (
    <div className="rise">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Eyebrow>Running</Eyebrow>
          <h1 className="mt-2.5 truncate text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
            {query}
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <span className="tnum text-2xl font-bold text-ink">
            {clock(elapsedMs)}
          </span>
          <button type="button" onClick={onCancel} className={ghostButton}>
            Stop
          </button>
        </div>
      </div>

      <div className="relative mt-5 h-[3px] overflow-hidden rounded-full bg-line sweep" />

      <div className="mt-8 grid gap-8 lg:grid-cols-[190px_1fr]">
        <div className="lg:sticky lg:top-8 lg:self-start">
          <StageRail active={active} />
        </div>

        <div className="min-w-0">
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
            {counters.map((counter) => (
              <div key={counter.label} className="bg-paper px-4 py-3">
                <dt className="eyebrow text-ink-50">{counter.label}</dt>
                <dd className="tnum mt-1 text-xl font-extrabold text-ink">
                  {counter.value || '–'}
                </dd>
              </div>
            ))}
          </dl>

          {sources.length > 0 && (
            <div className="mt-6">
              <Eyebrow tone="muted">Listings</Eyebrow>
              <div className="mt-2.5 flex flex-wrap gap-2">
                {sources.map((source) => (
                  <span
                    key={source.url}
                    title={source.detail || source.url}
                    className={`inline-flex items-center gap-2 rounded border px-2.5 py-1.5 text-xs font-semibold ${SOURCE_STYLE[source.status]}`}
                  >
                    {source.status === 'pending' && (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose" />
                    )}
                    {source.domain}
                  </span>
                ))}
              </div>
            </div>
          )}

          {photos.length > 0 && (
            <div className="mt-6">
              <Eyebrow tone="muted">
                Packaging photos being read ({photos.length})
              </Eyebrow>
              <div className="mt-2.5 grid grid-cols-5 gap-2 sm:grid-cols-8 lg:grid-cols-10">
                {photos.map((photo) => (
                  <Thumb
                    key={photo.url}
                    url={photo.url}
                    alt={photo.source}
                    scanning={reading}
                    className="aspect-square rise"
                  />
                ))}
              </div>
            </div>
          )}

          <div className="mt-6">
            <Eyebrow tone="muted">Activity</Eyebrow>
            <div
              ref={log}
              className="mt-2.5 max-h-80 overflow-y-auto rounded-lg border border-line bg-paper"
            >
              <ul className="divide-y divide-line">
                {events.map((event) => (
                  <li
                    key={event.seq}
                    className="rise flex gap-3 px-4 py-2.5 text-[13px]"
                  >
                    <span className="tnum shrink-0 pt-px font-mono text-[11px] text-ink-50">
                      {clock(event.at_ms)}
                    </span>
                    <span className="min-w-0">
                      <span className={`font-medium ${TONE_STYLE[event.tone]}`}>
                        {event.message}
                      </span>
                      {event.detail && (
                        <span className="text-ink-50"> — {event.detail}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              {!events.length && (
                <p className="px-4 py-6 text-[13px] text-ink-50">
                  Starting the run…
                </p>
              )}
            </div>
          </div>

          <p className="mt-4 text-xs text-ink-50">
            Reading the packaging photos is the slow part — a full run takes two
            to four minutes.
          </p>
        </div>
      </div>
    </div>
  );
}
