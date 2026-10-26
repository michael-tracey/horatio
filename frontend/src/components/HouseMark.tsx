/**
 * The ★ beside a troupe's own merit or flaw, wherever it shows, with its note:
 * "House merit of Night Court". `short` shows only the star, the note being its
 * name for screen readers and on hover. What its effects do (`summary`) shows on
 * hover too.
 */
export function HouseMark({ label, short = false, summary }: { label: string; short?: boolean; summary?: string | null }) {
  return (
    <span className="ml-1 inline-flex items-baseline gap-1 text-xs text-gold" title={summary ? `${label}. What it does: ${summary}` : label}>
      <span aria-hidden>★</span>
      {short ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </span>
  );
}

/** What a house merit's effects do, in a line under its description. */
export function HouseSummary({ summary }: { summary?: string | null }) {
  if (!summary) return null;
  return <span className="mt-0.5 block text-xs text-gold">What it does: {summary}</span>;
}
