import { useRef } from "react";
import { useNavigate } from "react-router";

/** How many taps open the card, and the most time between two of them, in ms. */
export const TAPS = 7;
export const GAP = 1500;

export type Taps = { count: number; last: number };
export const NO_TAPS: Taps = { count: 0, last: -Infinity };

/** One more tap at `now`: counted on from the last if it came soon enough, else
 * the first again. `open` says this one is the seventh; the count starts over. */
export function tapped(taps: Taps, now: number): Taps & { open: boolean } {
  const count = now - taps.last <= GAP ? taps.count + 1 : 1;
  return count >= TAPS ? { count: 0, last: now, open: true } : { count, last: now, open: false };
}

/** Whether a character on the troupe's list has a card: a vampire (one with a
 * social age) with a picture. */
export function hasCard(entry: { picture: string | null; social_age: string }): boolean {
  return !!entry.picture && ["Neonate", "Ancilla", "Elder"].includes(entry.social_age);
}

export function cardPath(characterId: string, troupeId?: string | null): string {
  return `/print/characters/${characterId}/jyhad${troupeId ? `?troupe=${troupeId}` : ""}`;
}

/**
 * The easter egg (#537): the click handler for a character's clan symbol (or, on
 * its page, its clan's name) that opens its Jyhad card on the seventh tap in a row.
 * Nothing shows that it can be tapped.
 */
export function useSevenTaps(characterId: string): () => void {
  const navigate = useNavigate();
  const taps = useRef<Taps>(NO_TAPS);
  return () => {
    const next = tapped(taps.current, Date.now());
    taps.current = next;
    if (next.open) navigate(cardPath(characterId));
  };
}
