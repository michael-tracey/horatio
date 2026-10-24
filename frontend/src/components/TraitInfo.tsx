import { useId, useState } from "react";
import type { ReactNode } from "react";

/** How a rules page reference reads: "p. 86" in the core book, or as the data gives it ("Vol. 2, p. 281"). */
export function pageLabel(page: string | null | undefined): string | null {
  const p = page?.trim();
  if (!p || p.toLowerCase() === "unknown") return null;
  if (!/^\d/.test(p)) return p;
  return `MET: VTM ${/[-&]/.test(p) ? "pp." : "p."} ${p}`;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}>
      <path d="M7.5 4.5 13 10l-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * A trait's name in its row, as a button with a chevron that opens a short panel
 * under the row with the `description` and the book page. Several can be open
 * at once. A trait with no description is just its name.
 *
 * It renders into the row's own container, a wrapping flex row or a grid: the
 * name (and whatever follows it on the same line, `after`), then the panel, which
 * takes a line of its own below the row's other cells. The panel follows the button in
 * the page, as a disclosure's does, and is shown last.
 */
export function TraitInfo({
  name,
  after,
  description,
  page,
}: {
  name: ReactNode;
  after?: ReactNode;
  description?: string | null;
  page?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const pageText = pageLabel(page);
  return (
    <>
      <span className="min-w-0">
        {description ? (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={id}
            onClick={() => setOpen(!open)}
            className="-ml-1 inline-flex items-center gap-1 rounded px-1 py-0.5 text-left hover:bg-ash/60"
          >
            <Chevron open={open} />
            {name}
          </button>
        ) : (
          name
        )}
        {after}
      </span>
      {description && open && (
        <div id={id} className="order-last col-span-full basis-full pb-1 pl-5 text-xs leading-relaxed text-mist">
          <p>{description}</p>
          {pageText && <p className="mt-0.5">{pageText}</p>}
        </div>
      )}
    </>
  );
}
