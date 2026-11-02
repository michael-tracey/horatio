/**
 * A troupe's own wording on a book trait (horatio.book_traits, issue #433): added to
 * the book's summary, or in its place. Always the troupe's text, never the book's.
 */
export type Wording = { wording: string; wording_mode: "added" | "replaces" };

/** The troupe's wording, if it gave the trait some. */
export function wordingOf(change: Partial<Wording> | null | undefined): Wording | null {
  const text = change?.wording?.trim();
  return text ? { wording: text, wording_mode: change?.wording_mode === "replaces" ? "replaces" : "added" } : null;
}

/** The book's summary as a player reads it in the troupe: none where the troupe's wording replaces it. */
export function bookSummary(description: string | null | undefined, change: Partial<Wording> | null | undefined): string | null {
  const wording = wordingOf(change);
  return wording?.wording_mode === "replaces" ? null : (description ?? null);
}

/** How the troupe's wording is labelled wherever it shows. */
export function wordingLabel(wording: Wording): string {
  return wording.wording_mode === "replaces" ? "House rule, in place of the book's" : "House rule";
}
