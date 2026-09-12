// Shared visual primitives. Everything the app draws sits on these, so the
// burgundy/paper palette stays in one place.

import { type ReactNode, useState } from 'react';
import { imageUrl, type Severity, type Status } from './api';

export const card = 'rounded-lg border border-line bg-paper';

export const button =
  'inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40';

export const primaryButton = `${button} bg-wine text-cream hover:bg-wine-dark`;

export const ghostButton = `${button} border border-line-strong bg-paper text-ink hover:bg-shell`;

export const field =
  'w-full rounded-md border border-line-strong bg-paper px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-ink-50 focus:border-rose focus:ring-2 focus:ring-rose/20';

export function Logo({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <title>ProductLens</title>
      <circle
        cx="12"
        cy="12"
        r="10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="15" cy="9.5" r="4.2" fill="currentColor" opacity="0.9" />
    </svg>
  );
}

export function Eyebrow({
  children,
  tone = 'rose',
}: {
  children: ReactNode;
  tone?: 'rose' | 'muted';
}) {
  return (
    <p className={`eyebrow ${tone === 'rose' ? 'text-rose' : 'text-ink-50'}`}>
      {children}
    </p>
  );
}

export const STATUS_LABEL: Record<Status, string> = {
  match: 'Match',
  minor: 'Minor',
  mismatch: 'Mismatch',
  missing: 'Missing',
};

const STATUS_CHIP: Record<Status, string> = {
  match: 'bg-ok-bg text-ok border-ok-line',
  minor: 'bg-warn-bg text-warn border-warn-line',
  mismatch: 'bg-bad-bg text-bad border-bad-line',
  missing: 'bg-gap-bg text-gap border-gap-line',
};

export function StatusChip({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border px-2 py-0.5 text-[11px] font-bold tracking-wide uppercase ${STATUS_CHIP[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

const SEVERITY_DOT: Record<Severity, string> = {
  high: 'bg-bad',
  medium: 'bg-gap',
  low: 'bg-warn',
  info: 'bg-line-strong',
};

export function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-70">
      <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[severity]}`} />
      {severity} severity
    </span>
  );
}

/** Product photo from a shop: proxy first, then the shop URL, then give up. */
export function Thumb({
  url,
  alt = '',
  className = '',
  scanning = false,
}: {
  url: string;
  alt?: string;
  className?: string;
  scanning?: boolean;
}) {
  const [src, setSrc] = useState(imageUrl(url));
  const [failed, setFailed] = useState(false);
  return (
    <span
      className={`relative block overflow-hidden rounded border border-line bg-shell ${
        scanning ? 'scan' : ''
      } ${className}`}
    >
      {failed ? (
        <span className="flex h-full w-full items-center justify-center p-1 text-center text-[10px] text-ink-50">
          no image
        </span>
      ) : (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          className="h-full w-full object-contain"
          onError={() => {
            if (src !== url) setSrc(url);
            else setFailed(true);
          }}
        />
      )}
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="eyebrow text-ink-50">{label}</dt>
      <dd className="tnum mt-1 text-lg font-bold text-ink">{value}</dd>
    </div>
  );
}

export const clock = (ms: number) => {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="bg-ink text-cream">
        <div className="mx-auto flex max-w-6xl items-center px-6 py-4">
          <a href="/" className="flex items-center gap-3 text-cream">
            <Logo className="h-7 w-7 text-rose" />
            <span className="text-xl font-extrabold tracking-tight">
              ProductLens
            </span>
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
    </div>
  );
}
