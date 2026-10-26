/** Retainers (core book p. 104): how their dots compare with the background's rating. */

/** A warning while the listed Retainers' dots and the background's rating disagree; null when they match. */
export function mismatch(rating: number, total: number): string | null {
  if (rating === total) return null;
  if (total < rating) {
    const spare = rating - total;
    return `${spare} ${spare === 1 ? "dot of the Retainers background is" : "dots of the Retainers background are"} not given to a Retainer yet.`;
  }
  const over = total - rating;
  return `The Retainers listed have ${over} more ${over === 1 ? "dot" : "dots"} than the Retainers background.`;
}

/** What the book says of a lost Retainer, for the note beside it. */
export const LOST_NOTE =
  "A lost Retainer's dots are out of reach for one game or two weeks, whichever is longer, for each dot, unless a replacement is found (p. 104). Staff decide when.";

export const LOST_WORDS: Record<string, string> = { released: "Released", killed: "Killed" };
