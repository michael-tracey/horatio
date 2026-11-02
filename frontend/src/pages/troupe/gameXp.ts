import type { GameXpSettings, XpLine } from "../../api/types";

/**
 * Game XP charts (issue #438): a troupe's chart of XP by earned-XP band and
 * attendance kind, its adjustments and monthly cap, as the editor holds them and
 * as awarding a game works each character's figure out. The server works it out
 * again when the award is made (horatio.game_xp); this is what staff see first.
 */

export type Band = GameXpSettings["bands"][number];
export type Adjustment = GameXpSettings["adjustments"][number];

/** The book's monthly guidance (MET: VtM core, p. 108), when the troupe sets no figure of its own. */
export const BOOK_MONTHLY = 10;

/** With nothing set: no chart, the session XP for everyone, warned past the book's 10 a month. */
export const DEFAULTS: GameXpSettings = {
  bands: [],
  adjustments: [],
  cap: "warn",
  monthly_xp: null,
  absentee: false,
  absentee_by_players: false,
  absentee_downtime: false,
  absentee_lookback_days: 60,
};

/** Charts to start from: Flat is the book's way, AIT's taper an example. */
export const PRESETS: { name: string; bands: Band[] }[] = [
  { name: "Flat", bands: [] },
  {
    name: "AIT taper",
    bands: [
      { up_to: 200, attended: 5, absentee: 4 },
      { up_to: 300, attended: 4, absentee: 3 },
      { up_to: 400, attended: 3, absentee: 2 },
      { up_to: 500, attended: 2, absentee: 1 },
      { up_to: null, attended: 1, absentee: 0 },
    ],
  },
];

/** "0–200", "201–300", "501+". */
export function bandLabel(bands: { up_to?: number | null }[], index: number): string {
  const low = index === 0 ? 0 : (bands[index - 1]?.up_to ?? 0) + 1;
  const top = bands[index]?.up_to;
  return top == null ? `${low}+` : `${low}–${top}`;
}

/** "+1", "−1", with a true minus. */
export function signed(n: number): string {
  return n >= 0 ? `+${n}` : `−${-n}`;
}

/** "Helped +1, once a month". */
export function adjustmentText(a: { name: string; amount: number; per_month?: number | null }): string {
  const times = a.per_month == null ? "" : a.per_month === 1 ? ", once a month" : a.per_month === 2 ? ", twice a month" : `, ${a.per_month} times a month`;
  return `${a.name} ${signed(a.amount)}${times}`;
}

/** How the monthly cap acts, in a few words. */
export function capText(settings: Pick<GameXpSettings, "cap" | "monthly_xp">): string {
  const limit = settings.monthly_xp ?? BOOK_MONTHLY;
  if (settings.cap === "off") return "Not limited";
  return settings.cap === "cap" ? `Capped at ${limit} a month: the excess isn't given` : `Warned past ${limit} a month, never refused`;
}

// --- the editor -----------------------------------------------------------------------------

/** A band as the editor holds it: what is typed, checked on saving. The last row has no top. */
export type BandRow = { upTo: string; attended: string; absentee: string };

export function toRows(bands: Band[]): BandRow[] {
  return bands.map((b) => ({ upTo: b.up_to == null ? "" : String(b.up_to), attended: String(b.attended), absentee: String(b.absentee) }));
}

const whole = (text: string) => (/^\d+$/.test(text.trim()) ? Number(text.trim()) : null);

/** The rows as the chart to save, or what is wrong with them. No rows is the Flat chart. */
export function fromRows(rows: BandRow[]): { bands: Band[]; error: null } | { bands: null; error: string } {
  const bands: Band[] = [];
  for (const [i, row] of rows.entries()) {
    const last = i === rows.length - 1;
    const attended = whole(row.attended);
    const absentee = whole(row.absentee);
    if (attended === null || absentee === null) return { bands: null, error: `Give band ${i + 1} its XP as whole numbers.` };
    if (last) {
      bands.push({ up_to: null, attended, absentee });
      continue;
    }
    const top = whole(row.upTo);
    if (top === null) return { bands: null, error: `Give band ${i + 1} the earned XP it goes up to.` };
    const before = bands[i - 1]?.up_to;
    if (before != null && top <= before) return { bands: null, error: `Band ${i + 1} must go higher than the one before.` };
    bands.push({ up_to: top, attended, absentee });
  }
  return { bands, error: null };
}

/** A new band, before the last (open) one, a hundred XP above the band before it; or a first band. */
export function addBand(rows: BandRow[]): BandRow[] {
  if (rows.length === 0) return [{ upTo: "", attended: "5", absentee: "4" }];
  const open = rows[rows.length - 1]!;
  const tops = rows.slice(0, -1).map((r) => whole(r.upTo) ?? 0);
  const top = (tops.length ? Math.max(...tops) : 0) + 100;
  return [...rows.slice(0, -1), { upTo: String(top), attended: open.attended, absentee: open.absentee }, open];
}

/** Take a band away. Taking the last away leaves the one before it open-topped. */
export function removeBand(rows: BandRow[], index: number): BandRow[] {
  const left = rows.filter((_, i) => i !== index);
  return left.map((r, i) => (i === left.length - 1 ? { ...r, upTo: "" } : r));
}

// --- awarding ------------------------------------------------------------------------------

/** What staff chose for one character: adjustments ticked, and a figure set by hand with its reason. */
export type Choice = { ticks: string[]; override: number | null; reason: string };

export const NO_CHOICE: Choice = { ticks: [], override: null, reason: "" };

/** How many more times an adjustment can be ticked for a character this month; null for no limit. */
export function usesLeft(adjustment: Adjustment, line: Pick<XpLine, "used">): number | null {
  if (adjustment.per_month == null) return null;
  return Math.max(0, adjustment.per_month - (line.used[adjustment.key] ?? 0));
}

/**
 * One character's XP for the game: the chart's figure for its band and kind (or the
 * flat amounts, with no chart), with the adjustments ticked, and the cap; or the
 * figure staff set by hand, which the cap doesn't hold back.
 */
export function figureFor(
  settings: GameXpSettings,
  line: Pick<XpLine, "kind" | "figure" | "month_xp">,
  flat: { attended: number; absentee: number },
  choice: Choice,
): { figure: number; amount: number; capped: number } {
  const figure = line.figure ?? (line.kind === "absentee" ? flat.absentee : flat.attended);
  if (choice.override !== null) return { figure, amount: choice.override, capped: 0 };
  const extra = settings.adjustments.filter((a) => choice.ticks.includes(a.key)).reduce((sum, a) => sum + a.amount, 0);
  const worked = Math.max(0, figure + extra);
  if (settings.cap !== "cap") return { figure, amount: worked, capped: 0 };
  const amount = Math.min(worked, Math.max(0, (settings.monthly_xp ?? BOOK_MONTHLY) - line.month_xp));
  return { figure, amount, capped: worked - amount };
}

/** Whether a troupe's game XP is as the book has it: no chart, adjustments or absentee games, and warned past 10. */
export function isBookWay(settings: GameXpSettings): boolean {
  return !settings.bands.length && !settings.adjustments.length && settings.cap === "warn" && settings.monthly_xp == null && !settings.absentee;
}
