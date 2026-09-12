import { type ReactNode, useState } from 'react';
import {
  type ImageRef,
  type PageStatus,
  proxiedImage,
  type Region,
} from './api';

export const card =
  'rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900';

export function Badge({
  children,
  tone = 'slate',
  title,
}: {
  children: ReactNode;
  tone?: 'slate' | 'green' | 'amber' | 'rose' | 'blue' | 'violet';
  title?: string;
}) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    green:
      'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
    amber: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300',
    rose: 'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-300',
    blue: 'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-300',
    violet:
      'bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-300',
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

const REGION_LABEL: Record<Region, string> = {
  rs: 'Srbija',
  regional: 'region',
  world: 'svet',
};

export function RegionBadge({ region }: { region: Region }) {
  return (
    <Badge
      tone={
        region === 'rs' ? 'blue' : region === 'regional' ? 'violet' : 'slate'
      }
    >
      {REGION_LABEL[region]}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: PageStatus }) {
  const tone =
    status === 'ok'
      ? 'green'
      : status === 'blocked'
        ? 'amber'
        : status === 'error'
          ? 'rose'
          : 'slate';
  const label =
    status === 'ok'
      ? 'skrejpovano'
      : status === 'blocked'
        ? 'blokirano'
        : status === 'error'
          ? 'greška'
          : 'preskočeno';
  return <Badge tone={tone}>{label}</Badge>;
}

export function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100">
        {title}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

function Thumb({ image }: { image: ImageRef }) {
  const [src, setSrc] = useState(proxiedImage(image.url));
  const [failed, setFailed] = useState(false);
  return (
    <a
      href={image.url}
      target="_blank"
      rel="noreferrer"
      title={`${image.role} · ${image.url}`}
      className="relative block aspect-square overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950"
    >
      {failed ? (
        <span className="flex h-full items-center justify-center p-1 text-center text-[10px] text-slate-400">
          slika se ne učitava
        </span>
      ) : (
        <img
          src={src}
          alt={image.role}
          loading="lazy"
          className="h-full w-full object-contain"
          onError={() => {
            // Proxy failed -> try the shop URL directly, then give up.
            if (src !== image.url) setSrc(image.url);
            else setFailed(true);
          }}
        />
      )}
      <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] text-white">
        {image.role}
      </span>
    </a>
  );
}

export function ImageGrid({ images }: { images: ImageRef[] }) {
  if (!images.length) {
    return (
      <p className="text-sm text-amber-700 dark:text-amber-400">
        Nema pronađenih slika na ovoj strani.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      {images.map((image) => (
        <Thumb key={image.url} image={image} />
      ))}
    </div>
  );
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd
        className="truncate text-sm text-slate-900 dark:text-slate-100"
        title={typeof value === 'string' ? value : undefined}
      >
        {value || <span className="text-slate-400">—</span>}
      </dd>
    </div>
  );
}

export function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText)
    return navigator.clipboard.writeText(text);
  return Promise.reject(new Error('Clipboard nije dostupan'));
}

export function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
