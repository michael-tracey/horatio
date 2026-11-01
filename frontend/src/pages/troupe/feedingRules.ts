/**
 * The optional Vol. 2 feeding rules' sums, as staff see them on a cycle's Feeding tab:
 * the book's number of Feeding Cards for the Rack (p. 306), and the simple challenges
 * against a poacher, one for each action spent patrolling (p. 305).
 */

export const MASQUERADE = [
  ["none", "No Masquerade trouble", 0],
  ["minor", "Minor Masquerade violations", -1],
  ["notable", "Notable Masquerade violations", -2],
  ["severe", "Severe Masquerade violations", -3],
] as const;

export const MOOD = [
  ["none", "An ordinary mood", 0],
  ["slightly", "Slightly festive", 1],
  ["notably", "Notably festive", 2],
  ["very", "Very festive", 3],
] as const;

export type Masquerade = (typeof MASQUERADE)[number][0];
export type Mood = (typeof MOOD)[number][0];

/** One card for each player and 2 more for every 5, changed by a tenth for each step of trouble or festivity, fractions up. As horatio.rack.suggested. */
export function suggestedCards(players: number, masquerade: Masquerade = "none", mood: Mood = "none"): number {
  const base = Math.ceil((players * 7) / 5);
  const tenths = 10 + MASQUERADE.find(([k]) => k === masquerade)![2] + MOOD.find(([k]) => k === mood)![2];
  return Math.max(0, Math.ceil((base * tenths) / 10));
}

export type Throw = "win" | "tie" | "lose";

/** A simple challenge, rock-paper-scissors against the Storyteller: a win, tie or loss, a third each. */
export function simpleChallenge(random: () => number = Math.random): Throw {
  const n = Math.floor(random() * 3);
  return n === 0 ? "win" : n === 1 ? "tie" : "lose";
}

/**
 * The patrollers who catch a poacher: one simple challenge for each action they spent
 * patrolling, and the poacher is caught by a patroller if it loses any of theirs.
 */
export function throwChallenges(patrols: { character_id: string; actions: number }[], random: () => number = Math.random): string[] {
  return patrols.filter((p) => Array.from({ length: p.actions }, () => simpleChallenge(random)).includes("lose")).map((p) => p.character_id);
}
