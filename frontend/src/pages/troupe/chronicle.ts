import type { components } from "../../api/schema";

/**
 * A troupe's chronicle (#711), shaped for its timeline: which date each event is
 * drawn at (in game or in Horatio), the rows (one per kind of event, or one per
 * character), the lanes a row needs so spans at the same time sit one above
 * another, and the stretch of time to show.
 */

export type ChronicleEvent = components["schemas"]["ChronicleEventOut"];
export type Kind = ChronicleEvent["kind"];

/** The kinds in the order their rows go, and the colour slot each keeps: a kind keeps its colour whatever is shown. */
export const KINDS: readonly { kind: Kind; label: string; slot: number }[] = [
  { kind: "title", label: "Titles", slot: 1 },
  { kind: "status", label: "Status", slot: 2 },
  { kind: "embrace", label: "Embraces", slot: 3 },
  { kind: "diablerie", label: "Diablerie", slot: 4 },
  { kind: "death", label: "Deaths", slot: 5 },
  { kind: "arrival", label: "Arrivals", slot: 6 },
  { kind: "departure", label: "Departures", slot: 7 },
];

export const kindOf = (kind: Kind) => KINDS.find((k) => k.kind === kind)!;

/** An in-game date ("1791-03-01") as a moment, at midnight UTC: a chronicle reaches back centuries. */
export function gameDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
  const at = new Date(Date.UTC(2000, m - 1, d));
  at.setUTCFullYear(y);
  return at;
}

/** An event where it is drawn: a moment (`to` null and not a span), or a span to `to`, open while `to` is null. */
export type Placed = { event: ChronicleEvent; from: Date; to: Date | null; span: boolean };

/**
 * Each event at its date: in game where its record keeps one, else in Horatio's
 * time. In game, an event with no in-game date, or a title ended with no in-game
 * end, can't be placed: it comes back in `undated`, to be listed rather than lost.
 */
export function placed(events: readonly ChronicleEvent[], inGame: boolean): { shown: Placed[]; undated: ChronicleEvent[] } {
  const shown: Placed[] = [];
  const undated: ChronicleEvent[] = [];
  for (const e of events) {
    const span = e.kind === "title";
    if (!inGame) {
      shown.push({ event: e, from: new Date(e.at), to: e.ends_at ? new Date(e.ends_at) : null, span });
      continue;
    }
    if (!e.on || (span && e.ends_at && !e.ends_on)) {
      undated.push(e);
      continue;
    }
    shown.push({ event: e, from: gameDate(e.on), to: e.ends_on ? gameDate(e.ends_on) : null, span });
  }
  return { shown, undated };
}

/**
 * The lane each item of a row takes: the first lane free when it begins, so spans
 * at the same time sit one above another. A moment takes no time, so moments share
 * a lane with whatever has ended by then.
 */
export function lanes<T extends { from: Date; to: Date | null; span: boolean }>(items: readonly T[], openEnd: Date): { placed: { item: T; lane: number }[]; count: number } {
  const ends: number[] = [];
  // sort() is stable: items at the same moment keep the order they came in, which is
  // the server's, by when each was recorded and then its id (#733).
  const out = [...items]
    .sort((a, b) => a.from.getTime() - b.from.getTime())
    .map((item) => {
      const start = item.from.getTime();
      let lane = ends.findIndex((end) => end <= start);
      if (lane === -1) lane = ends.length;
      ends[lane] = item.span ? (item.to ?? openEnd).getTime() : start;
      return { item, lane };
    });
  return { placed: out, count: Math.max(1, ends.length) };
}

export type Row = { key: string; label: string; lanes: number; items: { item: Placed; lane: number }[] };

/** One row per kind, in KINDS order, or one per character, in the order they first appear. Rows with nothing are left out. */
export function rows(shown: readonly Placed[], by: "kind" | "character", openEnd: Date): Row[] {
  const groups = new Map<string, { label: string; items: Placed[] }>();
  if (by === "kind") {
    for (const k of KINDS) groups.set(k.kind, { label: k.label, items: [] });
  }
  // Stable, as in lanes(): ties keep the server's order.
  const ordered = [...shown].sort((a, b) => a.from.getTime() - b.from.getTime());
  for (const p of ordered) {
    const key = by === "kind" ? p.event.kind : (p.event.character_id ?? `name:${p.event.character_name}`);
    const label = by === "kind" ? kindOf(p.event.kind).label : p.event.character_name;
    const group = groups.get(key) ?? { label, items: [] };
    group.items.push(p);
    groups.set(key, group);
  }
  const out: Row[] = [];
  for (const [key, { label, items }] of groups) {
    if (!items.length) continue;
    const { placed: packed, count } = lanes(items, openEnd);
    out.push({ key, label, lanes: count, items: packed.map(({ item, lane }) => ({ item, lane })) });
  }
  return out;
}

const DAY = 86_400_000;
const YEAR = 365.25 * DAY;

/**
 * The stretch of time all of it covers, at least a few days long, with a little
 * room either side so the first and last marks aren't cut in half. An open span
 * runs to `openEnd`.
 */
export function extent(shown: readonly Placed[], openEnd: Date): [Date, Date] {
  if (!shown.length) return [new Date(openEnd.getTime() - YEAR), openEnd];
  let first = Infinity;
  let last = -Infinity;
  for (const p of shown) {
    first = Math.min(first, p.from.getTime());
    last = Math.max(last, p.from.getTime(), p.span ? (p.to ?? openEnd).getTime() : p.from.getTime());
  }
  const pad = Math.max((last - first) * 0.02, 2 * DAY);
  return [new Date(first - pad), new Date(last + pad)];
}

export type Range = "all" | "century" | "decade" | "year";

export const RANGES: readonly { range: Range; label: string; years: number | null }[] = [
  { range: "all", label: "All of it", years: null },
  { range: "century", label: "Last 100 years", years: 100 },
  { range: "decade", label: "Last 10 years", years: 10 },
  { range: "year", label: "Last year", years: 1 },
];

/** The stretch to show for a range: the last so many years up to the end of `all`, never wider than all of it. */
export function rangeOf(all: [Date, Date], range: Range): [Date, Date] {
  const years = RANGES.find((r) => r.range === range)?.years ?? null;
  if (years === null) return all;
  const end = all[1];
  const start = new Date(Math.max(all[0].getTime(), end.getTime() - years * YEAR));
  return [start, end];
}
