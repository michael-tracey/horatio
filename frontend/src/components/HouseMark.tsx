/**
 * The ★ beside a troupe's own merit or flaw, wherever it shows, with its note:
 * "House merit of Night Court". `short` shows only the star, the note being its
 * name for screen readers and on hover.
 */
export function HouseMark({ label, short = false }: { label: string; short?: boolean }) {
  return (
    <span className="ml-1 inline-flex items-baseline gap-1 text-xs text-gold" title={label}>
      <span aria-hidden>★</span>
      {short ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </span>
  );
}
