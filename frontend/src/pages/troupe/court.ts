import type { components } from "../../api/schema";

/**
 * The court over time (#712), shaped for its chart: which dates a holding is drawn
 * with, the rows (one per title, in court order, grouped by sect), and the lanes
 * a row needs so that holders at the same time sit one above another.
 */

export type CourtHolding = components["schemas"]["HoldingOut"];
type CourtTitle = components["schemas"]["CourtTitleOut"];
type StatusLine = components["schemas"]["StatusLineOut"];

/** A holding with the dates it is drawn between; `to` is null while it is held. */
export type Dates = { holding: CourtHolding; from: Date; to: Date | null };

/** An in-game date ("1791-03-01") as a moment, at midnight UTC: a chronicle reaches back centuries. */
function gameDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
  const at = new Date(Date.UTC(2000, m - 1, d));
  at.setUTCFullYear(y);
  return at;
}

/**
 * The holdings to draw, and between which dates: the real ones, or the in-game
 * ones staff gave. In game, a holding without an in-game start, or ended without
 * an in-game end, can't be placed, so it is left out.
 */
export function dated(holdings: readonly CourtHolding[], inGame: boolean): Dates[] {
  const out: Dates[] = [];
  for (const h of holdings) {
    if (!inGame) {
      out.push({ holding: h, from: new Date(h.began_at), to: h.ended_at ? new Date(h.ended_at) : null });
      continue;
    }
    if (!h.began_in_game || (h.ended_at && !h.ended_in_game)) continue;
    out.push({ holding: h, from: gameDate(h.began_in_game), to: h.ended_in_game ? gameDate(h.ended_in_game) : null });
  }
  return out;
}

/**
 * The lane each holding of one title takes: the first lane free when it begins,
 * so holders at the same time (several Primogen) sit one above another, and one
 * after another share a lane. Returns each holding's lane and how many lanes.
 */
export function lanes(items: readonly Dates[], now = new Date()): { placed: { dates: Dates; lane: number }[]; count: number } {
  const ends: number[] = [];
  const placed = [...items]
    .sort((a, b) => a.from.getTime() - b.from.getTime())
    .map((dates) => {
      const start = dates.from.getTime();
      let lane = ends.findIndex((end) => end <= start);
      if (lane === -1) lane = ends.length;
      ends[lane] = (dates.to ?? now).getTime();
      return { dates, lane };
    });
  return { placed, count: Math.max(1, ends.length) };
}

export type CourtRow = {
  name: string;
  // Its sect's name on the first row of the sect, for a heading above it.
  sectStart: string | null;
  lanes: number;
  items: { dates: Dates; lane: number }[];
};

const NO_SECT = "Other titles";

/**
 * One row per title held, in court order, grouped by sect as the court order
 * first meets each one; a sect's heading on its first row. Titles with nothing to
 * draw (in game, none dated) are left out.
 */
export function courtRows(titles: readonly CourtTitle[], shown: readonly Dates[]): CourtRow[] {
  const bySect = new Map<string, CourtTitle[]>();
  for (const t of titles) {
    const sect = t.sect ?? NO_SECT;
    bySect.set(sect, [...(bySect.get(sect) ?? []), t]);
  }
  const rows: CourtRow[] = [];
  for (const [sect, inSect] of bySect) {
    let first = true;
    for (const t of inSect) {
      const mine = shown.filter((d) => d.holding.title === t.name);
      if (!mine.length) continue;
      const { placed, count } = lanes(mine);
      rows.push({ name: t.name, sectStart: first ? sect : null, lanes: count, items: placed });
      first = false;
    }
  }
  return rows;
}

/** The time and the most status the small charts of status share, so they compare. */
export function statusExtent(lines: readonly StatusLine[], now = new Date()): { start: Date; end: Date; most: number } {
  let start = now.getTime();
  let most = 1;
  for (const line of lines) {
    for (const p of line.points) {
      start = Math.min(start, new Date(p.at).getTime());
      most = Math.max(most, p.fleeting + p.negative);
    }
  }
  return { start: new Date(start), end: now, most };
}
