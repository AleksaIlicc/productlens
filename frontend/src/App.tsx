import { ghostButton, primaryButton, Shell } from './ui';
import { useRun } from './useRun';
import ReportView from './views/ReportView';
import RunView from './views/RunView';
import SearchView from './views/SearchView';
import SelectView from './views/SelectView';

function App() {
  const run = useRun();

  return (
    <Shell>
      {run.phase === 'idle' && <SearchView onSearch={run.search} />}

      {(run.phase === 'searching' || run.phase === 'comparing') && (
        <RunView
          title={run.query}
          eyebrow={run.phase === 'searching' ? 'Searching' : 'Auditing'}
          events={run.events}
          onCancel={run.phase === 'comparing' ? run.backToSelection : run.reset}
        />
      )}

      {run.phase === 'selecting' && (
        <SelectView
          query={run.query}
          products={run.products}
          suggested={run.suggested}
          stats={run.stats}
          onCompare={run.compare}
          onReset={run.reset}
        />
      )}

      {run.phase === 'done' && run.comparison && (
        <ReportView
          query={run.query}
          result={run.comparison}
          stats={run.stats}
          onChangeSelection={run.backToSelection}
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
            <button type="button" onClick={run.retry} className={primaryButton}>
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
