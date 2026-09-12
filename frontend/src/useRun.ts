// Drives the run in two halves: a search job, then — once the user has picked
// which channels matter — a comparison job. Both are polled the same way, and
// events accumulate so the run screen can replay the whole pipeline.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type CompareResponse,
  fetchJob,
  type JobEvent,
  type Product,
  type RunStats,
  startComparison,
  startSearch,
} from './api';

const POLL_MS = 700;

export type RunPhase =
  | 'idle'
  | 'searching'
  | 'selecting'
  | 'comparing'
  | 'done'
  | 'error';

type JobKind = 'search' | 'compare';

export type Run = {
  phase: RunPhase;
  query: string;
  events: JobEvent[];
  /** Everything the search turned up, the pool the picker works from. */
  products: Product[];
  suggested: string[];
  stats: RunStats | null;
  comparison: CompareResponse | null;
  error: string;
  search: (query: string) => void;
  compare: (listings: Product[]) => void;
  backToSelection: () => void;
  retry: () => void;
  reset: () => void;
};

export function useRun(): Run {
  const [phase, setPhase] = useState<RunPhase>('idle');
  const [query, setQuery] = useState('');
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [suggested, setSuggested] = useState<string[]>([]);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [error, setError] = useState('');
  // The job is state, not a ref: the poll loop must not start until the id of
  // the job it is meant to follow exists, or it polls the previous one.
  const [job, setJob] = useState<{ id: string; kind: JobKind } | null>(null);
  const lastSelection = useRef<Product[]>([]);

  useEffect(() => {
    if (!job) return;
    let stopped = false;
    let inFlight = false;
    let cursor = 0;

    const tick = async () => {
      // A poll slower than the interval would otherwise re-request events it
      // has already asked for, and append them twice.
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        const state = await fetchJob(job.id, cursor);
        if (stopped) return;
        cursor = state.cursor;
        if (state.events.length) {
          setEvents((prev) => {
            const seen = new Set(prev.map((event) => event.seq));
            const fresh = state.events.filter((event) => !seen.has(event.seq));
            return fresh.length ? [...prev, ...fresh] : prev;
          });
        }
        if (state.status === 'done') {
          const result = state.result;
          if (job.kind === 'search') {
            setProducts(result?.products ?? []);
            setSuggested(result?.suggested ?? []);
            setStats(result?.run ?? null);
            setPhase('selecting');
          } else if (result?.comparison) {
            setComparison(result.comparison);
            setPhase('done');
          } else {
            setError('The audit finished without producing a report.');
            setPhase('error');
          }
        } else if (state.status === 'error') {
          setError(state.error || 'The run failed.');
          setPhase('error');
        }
      } catch (err) {
        if (stopped) return;
        setError((err as Error).message);
        setPhase('error');
      } finally {
        inFlight = false;
      }
    };

    const timer = setInterval(tick, POLL_MS);
    void tick();
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [job]);

  const begin = useCallback(
    async (
      kind: JobKind,
      phaseName: RunPhase,
      start: () => Promise<{ job_id: string }>,
    ) => {
      setJob(null);
      setEvents([]);
      setError('');
      setPhase(phaseName);
      try {
        const { job_id } = await start();
        setJob({ id: job_id, kind });
      } catch (err) {
        setError((err as Error).message);
        setPhase('error');
      }
    },
    [],
  );

  const search = useCallback(
    (next: string) => {
      setQuery(next);
      setProducts([]);
      setComparison(null);
      void begin('search', 'searching', () => startSearch(next));
    },
    [begin],
  );

  const compare = useCallback(
    (listings: Product[]) => {
      lastSelection.current = listings;
      setComparison(null);
      void begin('compare', 'comparing', () => startComparison(listings));
    },
    [begin],
  );

  const backToSelection = useCallback(() => {
    setJob(null);
    setPhase('selecting');
    setEvents([]);
  }, []);

  // Whichever half failed is the one worth retrying.
  const retry = useCallback(() => {
    if (lastSelection.current.length >= 2 && products.length) {
      compare(lastSelection.current);
    } else if (query) {
      search(query);
    }
  }, [compare, products.length, query, search]);

  const reset = useCallback(() => {
    setJob(null);
    setPhase('idle');
    setEvents([]);
    setProducts([]);
    setSuggested([]);
    setStats(null);
    setComparison(null);
    setError('');
    setQuery('');
  }, []);

  return {
    phase,
    query,
    events,
    products,
    suggested,
    stats,
    comparison,
    error,
    search,
    compare,
    backToSelection,
    retry,
    reset,
  };
}
