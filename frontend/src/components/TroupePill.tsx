/**
 * A troupe as a small pill (#1153): what it goes by, its abbreviation, with its full name
 * as the pill's tooltip and as what a screen reader says. A long one (a troupe whose
 * abbreviation gave way to its name) is cut short with an ellipsis, so the pill never
 * takes more than its share of a row on a phone.
 */
export function TroupePill({ name, abbreviation, className = "" }: { name: string; abbreviation: string; className?: string }) {
  return (
    <span title={name} className={`inline-flex max-w-[40%] shrink-0 items-center rounded-full border border-ash px-2 py-0.5 text-xs leading-4 text-mist ${className}`}>
      <span aria-hidden="true" className="truncate">
        {abbreviation}
      </span>
      <span className="sr-only">{name}</span>
    </span>
  );
}
