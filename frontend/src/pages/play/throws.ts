/**
 * Rock, paper, scissors, which is how Mind's Eye Theatre resolves a test (MET: VTM
 * p. 271; "test", p. 21), thrown on the phone for the Play View's Throws tab (#668).
 * Each throw is made on the device alone and sent nowhere: tests are settled at
 * the table, with the players showing each other their screens.
 */

export const THROWS = ["rock", "paper", "scissors"] as const;
export type Throw = (typeof THROWS)[number];

export const THROW_NAMES: Record<Throw, string> = { rock: "Rock", paper: "Paper", scissors: "Scissors" };

/** A random whole number from 0 to 2³² − 1. */
export type RandomUint32 = () => number;

export const cryptoUint32: RandomUint32 = () => crypto.getRandomValues(new Uint32Array(1))[0]!;

/**
 * A whole number from 0 to `count` − 1, each as likely as the others. 2³² isn't a
 * multiple of 3, so taking the remainder of any draw would favour the low numbers
 * a little; a draw from the uneven top of the range is thrown away and drawn again.
 */
export function fairIndex(count: number, random: RandomUint32 = cryptoUint32): number {
  const range = 2 ** 32;
  const limit = range - (range % count);
  for (;;) {
    const draw = random();
    if (draw < limit) return draw % count;
  }
}

/** Rock, paper or scissors, each a third of the time. */
export function fairThrow(random: RandomUint32 = cryptoUint32): Throw {
  return THROWS[fairIndex(THROWS.length, random)]!;
}

/** What the count-in shows before the reveal, about a second in all. */
export const COUNT_IN = ["Rock…", "Paper…", "Scissors…"] as const;
export const COUNT_IN_STEP_MS = 330;

/** The count-in's steps for this person: none with reduced motion, so the throw shows at once. */
export function countIn(reducedMotion: boolean): readonly string[] {
  return reducedMotion ? [] : COUNT_IN;
}

export type Thrown = { throw: Throw; at: string };

/** How many past throws the tab keeps. */
export const KEPT = 3;

/** The latest throws, newest first, with `next` added and only the last few kept. */
export function remember(past: readonly Thrown[], next: Thrown): Thrown[] {
  return [next, ...past].slice(0, KEPT);
}

/** Throws kept for this browser tab, read safely: storage can be blocked, empty or hold something else. */
export function readThrows(raw: string | null): Thrown[] {
  try {
    const parsed: unknown = JSON.parse(raw ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((t): t is Thrown => !!t && THROWS.includes(t.throw) && typeof t.at === "string")
      .slice(0, KEPT);
  } catch {
    return [];
  }
}
