import type { Preferences } from "../api/types";
import { PAPERS, type Paper } from "../paper";

export type BadgeSize = Preferences["badge_size"];

/**
 * The badge sizes, for common badge holders, all portrait (#104). Each scales
 * the 3 × 5 in badge: `frame` its picture and spacing, `name` the name, `text`
 * the smaller text (standing, titles, status, the visible-traits band). On the
 * smallest, the smaller text shrinks most, so the name and picture keep their room.
 */
export const BADGE_SIZES: Record<BadgeSize, { label: string; width: number; height: number; frame: number; name: number; text: number }> = {
  "3x5": { label: "3 × 5 in", width: 3, height: 5, frame: 1, name: 1, text: 1 },
  "3x4": { label: "3 × 4 in", width: 3, height: 4, frame: 0.72, name: 0.9, text: 0.9 },
  cr80: { label: "ID card, 2.25 × 3.5 in", width: 2.25, height: 3.5, frame: 0.7, name: 0.72, text: 0.65 },
  "4x6": { label: "4 × 6 in", width: 4, height: 6, frame: 1.1, name: 1.2, text: 1.15 },
};

/**
 * When a badge holds more than its size has room for (a long name, several
 * titles, a crowded band), it is squeezed a step at a time until it fits: the
 * smaller text first, then the name and picture. Each step is [text, frame].
 */
export const SQUEEZE: [number, number][] = [
  [1, 1],
  [0.9, 1],
  [0.8, 1],
  [0.8, 0.9],
  [0.75, 0.8],
  [0.7, 0.7],
];

/** The least room left between the badges and the paper's edge, in inches: most
 * printers cannot print closer. Badges touch one another, sharing a cut line. */
export const EDGE = 0.25;

/** How many badges of a size go across and down the paper, and so to a page. */
export function grid(size: BadgeSize, paper: Paper): { columns: number; rows: number; perPage: number } {
  const badge = BADGE_SIZES[size];
  const page = PAPERS[paper];
  // A thousandth of an inch to spare, so a size that fits exactly is not lost to rounding.
  const fit = (room: number, each: number) => Math.max(1, Math.floor((room - 2 * EDGE + 0.001) / each));
  const columns = fit(page.width, badge.width);
  const rows = fit(page.height, badge.height);
  return { columns, rows, perPage: columns * rows };
}

/** Badges in pages of `perPage`; the last page may hold fewer. */
export function pages<T>(badges: T[], perPage: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < badges.length; i += perPage) out.push(badges.slice(i, i + perPage));
  return out;
}

const WORDS = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

/** "four to each US Letter page". */
export function perPageText(perPage: number, paper: Paper): string {
  return `${WORDS[perPage] ?? perPage} to each ${PAPERS[paper].name} page`;
}

/**
 * The name's size in points: the biggest text on the badge, as big as fits its
 * width, judged by the whole name and its longest word (a long word cannot wrap).
 */
export function nameSize(name: string, size: BadgeSize = "3x5"): number {
  const longestWord = Math.max(0, ...name.split(/\s+/).map((w) => w.length));
  const length = name.trim().length;
  const by = (chars: number) => (chars <= 8 ? 28 : chars <= 11 ? 24 : chars <= 14 ? 20 : chars <= 18 ? 17 : 14);
  // The whole name may wrap onto two lines, so it counts for half.
  const points = Math.min(by(longestWord), by(Math.ceil(length / 2)));
  return Math.round(points * BADGE_SIZES[size].name * 2) / 2;
}

/** The text under the name: "Toreador · Ancilla", or the age alone without a clan yet. */
export function standing(clan: string | null, age: string): string {
  return clan ? `${clan} · ${age}` : age;
}
