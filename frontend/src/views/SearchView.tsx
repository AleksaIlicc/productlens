import { useState } from 'react';
import { field, primaryButton } from '../ui';

export default function SearchView({
  onSearch,
  error,
}: {
  onSearch: (query: string) => void;
  error?: string;
}) {
  const [query, setQuery] = useState('');

  return (
    <div className="rise flex min-h-[70vh] flex-col items-center justify-center text-center">
      <h1 className="max-w-2xl text-4xl leading-[1.1] font-extrabold tracking-tight text-balance text-ink sm:text-5xl">
        Find the listing that contradicts your product.
      </h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const trimmed = query.trim();
          if (trimmed) onSearch(trimmed);
        }}
        className="mt-9 flex w-full max-w-xl flex-col gap-2.5 sm:flex-row"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Product name, brand and variant"
          aria-label="Product name"
          // biome-ignore lint/a11y/noAutofocus: the demo starts on this field
          autoFocus
          className={`${field} text-center sm:text-left`}
        />
        <button
          type="submit"
          disabled={!query.trim()}
          className={`${primaryButton} shrink-0 sm:w-40`}
        >
          Run check
        </button>
      </form>

      {error && (
        <p className="mt-6 max-w-xl rounded-md border border-bad-line bg-bad-bg px-3.5 py-2.5 text-sm text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
