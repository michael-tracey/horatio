/** Two badges to a US Letter page (3 × 5 in each, side by side). */
export const PER_PAGE = 2;

/** Badges in pages of two; the last page may hold one. */
export function pages<T>(badges: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < badges.length; i += PER_PAGE) out.push(badges.slice(i, i + PER_PAGE));
  return out;
}

/**
 * The name's size in points: the biggest text on the badge, as big as fits its
 * 2.7 in width, judged by the whole name and its longest word (a long word
 * cannot wrap).
 */
export function nameSize(name: string): number {
  const longestWord = Math.max(0, ...name.split(/\s+/).map((w) => w.length));
  const length = name.trim().length;
  const by = (chars: number) => (chars <= 8 ? 28 : chars <= 11 ? 24 : chars <= 14 ? 20 : chars <= 18 ? 17 : 14);
  // The whole name may wrap onto two lines, so it counts for half.
  return Math.min(by(longestWord), by(Math.ceil(length / 2)));
}

/** The text under the name: "Toreador · Ancilla", or the age alone without a clan yet. */
export function standing(clan: string | null, age: string): string {
  return clan ? `${clan} · ${age}` : age;
}
