// Drives one analysis job: kick it off, then poll for whatever the backend
// has reported since the last cursor. Events accumulate so the run screen can
// replay the whole pipeline, not just the latest line.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type AnalyzeResult,
  fetchJob,
  type JobEvent,
  type Product,
  startAnalysis,
  startComparison,
} from './api';

const POLL_MS = 700;

export type RunPhase = 'idle' | 'running' | 'done' | 'error';

export type Run = {
  phase: RunPhase;
  query: string;
  events: JobEvent[];
  elapsedMs: number;
  result: AnalyzeResult | null;
  /** Listings from the last full search, kept across re-comparisons. */
  pool: Product[];
  error: string;
  analyze: (query: string) => void;
  compare: (a: Product, b: Product, query: string) => void;
  reset: () => void;
};

export function useRun(): Run {
  const [phase, setPhase] = useState<RunPhase>('idle');
  const [query, setQuery] = useState('');
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [elapsedMs, setElapsed] = useState(0);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [pool, setPool] = useState<Product[]>([]);
  const [error, setError] = useState('');
  const jobId = useRef<string | null>(null);

  // Polling and the ticking clock both hang off this job id.
  useEffect(() => {
    if (phase !== 'running') return;
    let stopped = false;
    let inFlight = false;
    let cursor = 0;

    const tick = async () => {
      const id = jobId.current;
      // A poll slower than the interval would otherwise re-request events it
      // has already asked for, and append them twice.
      if (!id || stopped || inFlight) return;
      inFlight = true;
      try {
        const state = await fetchJob(id, cursor);
        if (stopped) return;
        cursor = state.cursor;
        setElapsed(state.elapsed_ms);
        if (state.events.length) {
          setEvents((prev) => {
            const seen = new Set(prev.map((event) => event.seq));
            const fresh = state.events.filter((event) => !seen.has(event.seq));
            return fresh.length ? [...prev, ...fresh] : prev;
          });
        }
        if (state.status === 'done') {
          setResult(state.result);
          // Only a full search carries run stats; a re-compare returns just
          // its own pair, so it must not shrink the pool.
          if (state.result?.run) setPool(state.result.products);
          setPhase('done');
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
  }, [phase]);

  const begin = useCallback(
    async (label: string, start: () => Promise<{ job_id: string }>) => {
      setQuery(label);
      setEvents([]);
      setElapsed(0);
      setResult(null);
      setError('');
      setPhase('running');
      try {
        const { job_id } = await start();
        jobId.current = job_id;
      } catch (err) {
        setError((err as Error).message);
        setPhase('error');
      }
    },
    [],
  );

  const analyze = useCallback(
    (next: string) => void begin(next, () => startAnalysis(next)),
    [begin],
  );

  const compare = useCallback(
    (a: Product, b: Product, label: string) =>
      void begin(label, () => startComparison(a, b)),
    [begin],
  );

  const reset = useCallback(() => {
    jobId.current = null;
    setPhase('idle');
    setEvents([]);
    setResult(null);
    setPool([]);
    setError('');
    setQuery('');
  }, []);

  return {
    phase,
    query,
    events,
    elapsedMs,
    result,
    pool,
    error,
    analyze,
    compare,
    reset,
  };
}
