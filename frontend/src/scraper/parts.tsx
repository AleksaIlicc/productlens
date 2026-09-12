import { type ReactNode, useState } from 'react';
import {
  type ImageRef,
  type PageStatus,
  proxiedImage,
  type Region,
} from './api';

export const card = 'rounded-lg border border-line bg-paper';

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
    slate: 'bg-shell text-ink-70 border-line-strong',
    green: 'bg-ok-bg text-ok border-ok-line',
    amber: 'bg-warn-bg text-warn border-warn-line',
    rose: 'bg-bad-bg text-bad border-bad-line',
    blue: 'bg-rose-pale text-wine border-bad-line',
    violet: 'bg-gap-bg text-gap border-gap-line',
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

const REGION_LABEL: Record<Region, string> = {
  rs: 'Serbia',
  regional: 'regional',
  world: 'international',
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

const STATUS_BADGE: Record<
  PageStatus,
  { tone: 'green' | 'amber' | 'rose'; label: string }
> = {
  ok: { tone: 'green', label: 'scraped' },
  blocked: { tone: 'amber', label: 'blocked' },
  error: { tone: 'rose', label: 'error' },
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { tone, label } = STATUS_BADGE[status];
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
      <summary className="cursor-pointer text-sm font-semibold text-ink-70 hover:text-ink">
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
      className="relative block aspect-square overflow-hidden rounded border border-line bg-shell"
    >
      {failed ? (
        <span className="flex h-full items-center justify-center p-1 text-center text-[10px] text-ink-50">
          image failed to load
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
      <span className="absolute top-1 left-1 rounded bg-ink/70 px-1 text-[10px] text-cream">
        {image.role}
      </span>
    </a>
  );
}

export function ImageGrid({ images }: { images: ImageRef[] }) {
  if (!images.length) {
    return <p className="text-sm text-warn">No images found on this page.</p>;
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
      <dt className="eyebrow text-ink-50">{label}</dt>
      <dd
        className="truncate text-sm text-ink"
        title={typeof value === 'string' ? value : undefined}
      >
        {value || <span className="text-ink-50">—</span>}
      </dd>
    </div>
  );
}

export function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText)
    return navigator.clipboard.writeText(text);
  return Promise.reject(new Error('Clipboard is not available'));
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
