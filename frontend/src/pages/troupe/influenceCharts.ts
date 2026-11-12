import type { ChartCycleOut, ChartEntryOut, HoldingOut } from "../../api/types";
import { TYPE_NAMES, type InfluenceType } from "../../influence";

/*
 * The influence log's charts (#710), shaped from the log's entries: a heatmap of
 * actions by specialisation and month, a web of who aimed conflict actions at
 * whom, who holds what influence now, and actions in each downtime cycle. Pure
 * data, no d3, so each shape is tested on its own.
 */

/** Elite, Underworld, or both together. */
export type TypeChoice = InfluenceType | "both";

/** What a heatmap cell counts: actions taken, or the levels of the general actions among them. */
export type Measure = "actions" | "levels";

const NO_SPECIALIZATION = "No specialisation";

export function ofType(entries: readonly ChartEntryOut[], type: TypeChoice): ChartEntryOut[] {
  return type === "both" ? [...entries] : entries.filter((e) => e.type === type);
}

/** The month an entry happened in, as "2026-07" (UTC, so a chart reads the same everywhere). */
export function monthOf(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Every month from `first` to `last`, inclusive, as "2026-07". */
export function monthsBetween(first: string, last: string): string[] {
  const found: string[] = [];
  let [y, m] = first.split("-").map(Number) as [number, number];
  const [ly, lm] = last.split("-").map(Number) as [number, number];
  while (y < ly || (y === ly && m <= lm)) {
    found.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return found;
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Jul 26" for "2026-07". */
export function monthLabel(month: string): string {
  const [y, m] = month.split("-");
  return `${MONTH_NAMES[Number(m) - 1]} ${y!.slice(2)}`;
}

/** What one entry adds to a cell: how many times it was taken, or that times its level. */
export function weight(entry: ChartEntryOut, measure: Measure): number {
  if (measure === "actions") return entry.times;
  return entry.level ? entry.level * entry.times : 0;
}

export type HeatRow = { key: string; label: string; total: number };
export type HeatCell = { row: string; month: string; value: number; entries: ChartEntryOut[] };
export type Heatmap = { rows: HeatRow[]; months: string[]; cells: HeatCell[]; max: number };

/**
 * Actions by specialisation (rows, busiest first) and month (columns, every month
 * from the first entry to the last), counted or by level. With both types, a row
 * says which ("News Media (Elite)"), since each type has its own specialisations.
 */
export function heatmap(entries: readonly ChartEntryOut[], type: TypeChoice, measure: Measure): Heatmap {
  const shown = ofType(entries, type).filter((e) => weight(e, measure) > 0);
  if (shown.length === 0) return { rows: [], months: [], cells: [], max: 0 };
  const label = (e: ChartEntryOut) => {
    const spec = e.specialization || NO_SPECIALIZATION;
    return type === "both" ? `${spec} (${TYPE_NAMES[e.type]})` : spec;
  };
  const key = (e: ChartEntryOut) => `${e.type}|${e.specialization}`;
  const cells = new Map<string, HeatCell>();
  const rows = new Map<string, HeatRow>();
  const months = shown.map((e) => monthOf(e.happened_at)).sort();
  for (const e of shown) {
    const row = key(e);
    const month = monthOf(e.happened_at);
    const id = `${row}@${month}`;
    const cell = cells.get(id) ?? { row, month, value: 0, entries: [] };
    cell.value += weight(e, measure);
    cell.entries.push(e);
    cells.set(id, cell);
    const r = rows.get(row) ?? { key: row, label: label(e), total: 0 };
    r.total += weight(e, measure);
    rows.set(row, r);
  }
  const ordered = [...rows.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label));
  const all = [...cells.values()];
  return { rows: ordered, months: monthsBetween(months[0]!, months.at(-1)!), cells: all, max: Math.max(...all.map((c) => c.value)) };
}

// --- the conflict web ------------------------------------------------------------------

/** Against (Attack), for (Boost, Defend), or a Block on an activity. */
export type LinkKind = "against" | "support" | "block";

const KINDS: Record<string, LinkKind> = { attack: "against", boost: "support", defend: "support", block: "block" };

export type WebNode = {
  key: string;
  name: string;
  characterId: string | null;
  kind: "character" | "name" | "activity";
  // Actions this one aimed at others, and others at it, by times taken.
  out: number;
  in: number;
  // Discovery blocks it placed to hide its own actions.
  discovery: number;
};

export type WebLink = {
  source: string;
  target: string;
  kind: LinkKind;
  // Times taken, over every entry between the two.
  weight: number;
  specializations: string[];
  entries: string[];
};

export type Web = { nodes: WebNode[]; links: WebLink[] };

function actorKey(characterId: string | null | undefined, name: string): string {
  return characterId ? `c:${characterId}` : `n:${name.trim().toLocaleLowerCase()}`;
}

/**
 * Who aimed conflict actions at whom: an Attack against someone, a Boost or a
 * Defend for someone, a Block on an activity. A Defend of one's own influence,
 * and an action whose target isn't known, link nobody; discovery blocks count on
 * whoever placed them.
 */
export function conflictWeb(entries: readonly ChartEntryOut[], type: TypeChoice): Web {
  const nodes = new Map<string, WebNode>();
  const links = new Map<string, WebLink>();
  const node = (key: string, name: string, characterId: string | null, kind: WebNode["kind"]) => {
    const found = nodes.get(key) ?? { key, name, characterId, kind, out: 0, in: 0, discovery: 0 };
    nodes.set(key, found);
    return found;
  };
  for (const e of ofType(entries, type)) {
    if (!e.conflict || !e.action_key) continue;
    const actor = node(actorKey(e.character_id, e.name), e.name, e.character_id ?? null, e.character_id ? "character" : "name");
    if (e.action_key === "discovery_block") {
      actor.discovery += e.times;
      continue;
    }
    const kind = KINDS[e.action_key];
    if (!kind) continue;
    let target: WebNode | null = null;
    if (kind === "block") {
      const activity = e.target_activity.trim();
      if (activity) target = node(`a:${activity.toLocaleLowerCase()}`, activity, null, "activity");
    } else if (e.target_character_id || e.target_name.trim()) {
      target = node(actorKey(e.target_character_id, e.target_name), e.target_name, e.target_character_id ?? null, e.target_character_id ? "character" : "name");
    }
    if (!target || target.key === actor.key) continue;
    actor.out += e.times;
    target.in += e.times;
    const id = `${actor.key}>${target.key}>${kind}`;
    const link = links.get(id) ?? { source: actor.key, target: target.key, kind, weight: 0, specializations: [], entries: [] };
    link.weight += e.times;
    if (e.specialization && !link.specializations.includes(e.specialization)) link.specializations.push(e.specialization);
    link.entries.push(e.short_id);
    links.set(id, link);
  }
  // Someone with only discovery blocks has no one to link to: leave them out.
  const linked = new Set([...links.values()].flatMap((l) => [l.source, l.target]));
  return { nodes: [...nodes.values()].filter((n) => linked.has(n.key)), links: [...links.values()] };
}

// --- who holds what --------------------------------------------------------------------

export type HoldingLeaf = { name: string; characterId: string; type: InfluenceType; rating: number; specializations: string[] };
export type HoldingGroup = { name: string; type: InfluenceType; total: number; children: HoldingLeaf[] };
export type HoldingTree = { name: string; children: HoldingGroup[] };

/** Influence ratings by type, then character, largest first, for a treemap; types and characters with none are left out. */
export function holdingsTree(holdings: readonly HoldingOut[], type: TypeChoice): HoldingTree {
  const types: InfluenceType[] = type === "both" ? ["elite", "underworld"] : [type];
  const children = types
    .map((t) => {
      const leaves = holdings
        .map((h) => ({
          name: h.name,
          characterId: h.character_id,
          type: t,
          rating: t === "elite" ? h.elite : h.underworld,
          specializations: t === "elite" ? h.elite_specializations : h.underworld_specializations,
        }))
        .filter((l) => l.rating > 0)
        .sort((a, b) => b.rating - a.rating || a.name.localeCompare(b.name));
      return { name: TYPE_NAMES[t], type: t, total: leaves.reduce((n, l) => n + l.rating, 0), children: leaves };
    })
    .filter((g) => g.children.length > 0);
  return { name: "Influence", children };
}

// --- actions per cycle -----------------------------------------------------------------

export type CycleRow = { id: string; name: string; elite: number; underworld: number };
export type PerCycle = { rows: CycleRow[]; outside: number };

/**
 * Actions taken in each downtime cycle, oldest first, by type. An entry logged
 * against a cycle counts there; one without (a game's tap, staff by hand) counts
 * in the cycle whose window it fell in, from the cycle before's close to this
 * one's. Entries after the last close count in `outside`.
 */
export function perCycle(entries: readonly ChartEntryOut[], cycles: readonly ChartCycleOut[]): PerCycle {
  const ordered = [...cycles].sort((a, b) => a.closes_at.localeCompare(b.closes_at));
  const rows: CycleRow[] = ordered.map((c) => ({ id: c.id, name: c.name, elite: 0, underworld: 0 }));
  const byId = new Map(rows.map((r) => [r.id, r]));
  const closes = ordered.map((c) => new Date(c.closes_at).getTime());
  let outside = 0;
  for (const e of entries) {
    let row = e.cycle_id ? byId.get(e.cycle_id) : undefined;
    if (!row) {
      const at = new Date(e.happened_at).getTime();
      const i = closes.findIndex((close) => at <= close);
      row = i >= 0 ? rows[i] : undefined;
    }
    if (row) row[e.type] += e.times;
    else outside += e.times;
  }
  return { rows, outside };
}
