import type { LanguagesOut } from "../../api/types";

export type LanguageMode = LanguagesOut["mode"];

/** The charts a troupe can play, in the order offered. */
export const LANGUAGE_MODES: { value: LanguageMode; label: string; meaning: string }[] = [
  { value: "book", label: "Book", meaning: "One language for each dot of Linguistics (p. 95)." },
  { value: "accelerated", label: "Accelerated chart", meaning: "More languages at each dot: 1, 2, 4, 8, 16, 24 and 32 at Linguistics 1 to 7." },
  { value: "custom", label: "Custom", meaning: "The troupe's own number of languages at each rating." },
];

/** The most languages one rating may give, as the backend allows. */
export const MOST_LANGUAGES = 999;

/** The figures the custom editor starts from: the troupe's own chart if it has one, else the chart in use, one for each rating. */
export function startingFigures(data: Pick<LanguagesOut, "custom" | "table" | "max_rating">): string[] {
  const from = data.custom.length ? data.custom : data.table;
  return Array.from({ length: data.max_rating }, (_, i) => String(from[Math.min(i, from.length - 1)] ?? i + 1));
}

/** The custom chart as typed, or why it cannot be saved. */
export function readFigures(figures: string[]): { table: number[]; error: null } | { table: null; error: string } {
  const table: number[] = [];
  for (const [i, text] of figures.entries()) {
    const n = Number(text.trim());
    if (text.trim() === "" || !Number.isInteger(n) || n < 0 || n > MOST_LANGUAGES) {
      return { table: null, error: `Give Linguistics ${i + 1} a whole number of languages from 0 to ${MOST_LANGUAGES}.` };
    }
    if (table.length && n < table[table.length - 1]!) {
      return { table: null, error: `Linguistics ${i + 1} cannot give fewer languages than Linguistics ${i}.` };
    }
    table.push(n);
  }
  return { table, error: null };
}

/** The languages at each rating from 1 to `max`, a chart's last figure carrying on, or one a dot with no chart. */
export function ratingsOf(chart: number[] | null, max: number): number[] {
  return Array.from({ length: max }, (_, i) => (chart?.length ? chart[Math.min(i, chart.length - 1)]! : i + 1));
}

/** The chart a mode plays, for the preview: the accelerated preset, the custom figures, or the book's (null). */
export function chartFor(mode: LanguageMode, accelerated: number[], custom: number[] | null): number[] | null {
  if (mode === "accelerated") return accelerated;
  if (mode === "custom") return custom;
  return null;
}
