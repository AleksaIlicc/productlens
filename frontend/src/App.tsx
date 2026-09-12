import type { AnalyzeResult, Product } from './api';
import { ghostButton, primaryButton, Shell } from './ui';
import { useRun } from './useRun';
import ReportView from './views/ReportView';
import RunView from './views/RunView';
import SearchView from './views/SearchView';

/** A re-compare returns only its own pair; keep the wider search pool so the
 * report's picker still offers every listing the search found. */
function withPool(result: AnalyzeResult, pool: Product[]): AnalyzeResult {
  const products = new Map(pool.map((product) => [product.id, product]));
  for (const product of result.products) products.set(product.id, product);
  return { ...result, products: [...products.values()] };
}

function App() {
  const run = useRun();

  return (
    <Shell>
      {run.phase === 'idle' && <SearchView onSearch={run.analyze} />}

      {run.phase === 'running' && (
        <RunView
          query={run.query}
          events={run.events}
          elapsedMs={run.elapsedMs}
          onCancel={run.reset}
        />
      )}

      {run.phase === 'done' && run.result && (
        <ReportView
          result={withPool(run.result, run.pool)}
          onCompare={(a, b) => run.compare(a, b, run.query)}
          onReset={run.reset}
        />
      )}

      {run.phase === 'error' && (
        <div className="rise max-w-2xl">
          <p className="eyebrow text-bad">Run failed</p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-ink">
            The run stopped before it finished.
          </h1>
          <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3.5 py-2.5 font-mono text-[13px] break-words text-bad">
            {run.error}
          </p>
          <div className="mt-6 flex gap-2.5">
            <button
              type="button"
              onClick={() => run.analyze(run.query)}
              className={primaryButton}
            >
              Try again
            </button>
            <button type="button" onClick={run.reset} className={ghostButton}>
              New search
            </button>
          </div>
        </div>
      )}
    </Shell>
  );
}

export default App;
