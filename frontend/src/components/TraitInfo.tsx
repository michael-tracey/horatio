import { useId, useState } from "react";
import type { ReactNode } from "react";
import { bookSummary, wordingOf, type Wording } from "../houseWording";
import { isSrdPage, SRD_NAME } from "../pages/troupe/bookPage";
import { HouseWording } from "./TroupeChange";

/** How a rules page reference reads: "p. 86" in the core book, as the data gives it ("Vol. 2, p. 281"), or the SRD's name for a link to it. */
export function pageLabel(page: string | null | undefined): string | null {
  const p = page?.trim();
  if (!p || p.toLowerCase() === "unknown") return null;
  if (isSrdPage(p)) return SRD_NAME;
  if (!/^\d/.test(p)) return p;
  return `MET: VTM ${/[-&]/.test(p) ? "pp." : "p."} ${p}`;
}

/** A page reference as `text` reads it, or, for a page of the V20 LARP SRD, a link to it named for the SRD. */
export function PageRef({ page, text = pageLabel }: { page: string | null | undefined; text?: (page: string) => string | null }) {
  const p = page?.trim();
  if (!p) return null;
  if (isSrdPage(p)) {
    return (
      <a href={p} target="_blank" rel="noreferrer" className="text-gold underline hover:text-parchment">
        {SRD_NAME}
      </a>
    );
  }
  return <>{text(p)}</>;
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
 * under the row with the `description`, anything `more` (a discipline's powers),
 * and the book page. Several can be open at once. A trait with nothing to say is
 * just its name.
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
  more,
  page,
  summary,
  wording,
}: {
  name: ReactNode;
  after?: ReactNode;
  description?: string | null;
  more?: ReactNode;
  page?: string | null;
  /** A house merit's "what it does", from its effects: under the description. */
  summary?: string | null;
  /** The troupe's own wording for a book trait: added to the description, or in its place. */
  wording?: Partial<Wording> | null;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const pageText = pageLabel(page);
  const says = Boolean(description || more || summary || wordingOf(wording));
  const shown = bookSummary(description, wording);
  return (
    <>
      <span className="min-w-0">
        {says ? (
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
      {says && open && (
        <div id={id} className="order-last col-span-full basis-full pb-1 pl-5 text-xs leading-relaxed text-mist">
          {shown && <p>{shown}</p>}
          <HouseWording change={wording} className="my-1" />
          {summary && <p className="text-gold">What it does: {summary}</p>}
          {more}
          {pageText && (
            <p className="mt-0.5">
              <PageRef page={page} />
            </p>
          )}
        </div>
      )}
    </>
  );
}
