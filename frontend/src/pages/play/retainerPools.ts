/** What the book says of a Retainer at a game (MET: VtM core p. 105), in short. */

/** A skill specialty adds this to the Retainer's pool. */
export const SPECIALTY_BONUS = 5;

export const NO_WILLPOWER = "No Willpower, and no retests unless it overbids (p. 105).";

export const HEALTH_NOTE = "Out of health levels: unconscious, or in too much pain to act. Not dead, but it may die without care.";

/** A ghoul's Blood: what it can spend, and what it can't. */
export function bloodNote(): string {
  return "Potent Blood, spent 1 a round to heal or use its discipline. It also has 5 mortal Blood it cannot spend.";
}

/** Pools as one line, for the printed sheet: "Pool 8 · Brawl 13, Stealth 13". */
export function poolLine(r: { pool: number; specialties: string[] }): string {
  const special = r.specialties.map((s) => `${s} ${r.pool + SPECIALTY_BONUS}`);
  return [`Pool ${r.pool}`, ...(special.length ? [special.join(", ")] : [])].join(" · ");
}
