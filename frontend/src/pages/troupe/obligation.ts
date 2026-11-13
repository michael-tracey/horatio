import type { BondWebOut, SireLineNodeOut } from "../../api/types";
import { network, weightsOf, type Statistics } from "../../boonStatistics";
import { KINDS, type BoonKind } from "../../boons";
import { clanKey } from "../../charts/clans";
import { bondWeb } from "./bondWeb";

/*
 * One web of obligation (#709): what ties a troupe's characters together, each
 * kind of tie a layer staff can switch on and off. Boons, blood bonds and sire
 * lines each come from their own chart's data (#702, #708, #707), shaped by that
 * chart's own functions, then laid on one set of people here. Plain functions, so
 * the tests can check the merging without drawing anything.
 */

export type Layer = "boons" | "bonds" | "sires";

export const LAYERS: { value: Layer; label: string }[] = [
  { value: "boons", label: "Boons" },
  { value: "bonds", label: "Blood bonds" },
  { value: "sires", label: "Sire lines" },
];

/** What each layer's data is: any of them may be missing, when the troupe doesn't keep it or the reader may not see it. */
export type Sources = {
  boons?: Pick<Statistics, "nodes" | "links" | "weights">;
  bonds?: Pick<BondWebOut, "people" | "bonds">;
  sires?: { nodes: readonly SireLineNodeOut[] };
};

export type Filters = {
  layers: ReadonlySet<Layer>;
  // Everyone, or only those still in play (and names only), on both sides of a tie.
  who: "active" | "everyone";
  // Only ties with someone of this clan on either side.
  clan: string | null;
  // Only ties with a title holder on either side.
  titled: boolean;
  // Boons: hide links lighter than this, as on the boons network.
  boonMinimum: number;
  // Blood bonds: ended and broken bonds too, drawn faintly.
  endedBonds: boolean;
};

export const DEFAULT_FILTERS: Filters = {
  layers: new Set(LAYERS.map((l) => l.value)),
  who: "active",
  clan: null,
  titled: false,
  boonMinimum: 0,
  endedBonds: false,
};

/** One tie between two people, `from` → `to`: debtor to creditor, thrall to regnant, sire to childe. */
export type Tie = {
  key: string;
  layer: Layer;
  from: string;
  to: string;
  // Still in force: an open boon, a felt bond, a sire. Fading, ended and broken bonds are not.
  open: boolean;
  // Boons: how many, their weight with the troupe's weights, and the heaviest kind.
  count?: number;
  weight?: number;
  kind?: BoonKind;
  kinds?: Record<string, number>;
  // Blood bonds: the level and its state.
  level?: number;
  status?: string;
  fadesOn?: string | null;
};

export type Person = {
  key: string;
  character_id: string | null;
  name: string;
  clan: string | null;
  // active, or how they left play: final_death | off_field | inactive | retired. A name only counts as active.
  standing: string;
  titles: string[];
  // Measured on the ties shown.
  owes: number;
  owed: number;
  thralls: number;
  boundTo: number;
  childer: number;
  sire: string | null;
};

export type ObligationWeb = { people: Person[]; ties: Tie[] };

/**
 * One key per person across every layer: a character by its id, a name only by its
 * name in lower case, so "Old Marguerite" owed a boon and bound by blood is one dot.
 */
export function personKey(characterId: string | null | undefined, name: string): string {
  return characterId ? characterId : `name:${name.trim().toLowerCase()}`;
}

type Seen = Omit<Person, "owes" | "owed" | "thralls" | "boundTo" | "childer" | "sire">;

/** Gathers people from every source: what one source knows (a clan, titles, how they left) fills what another lacks. */
class People {
  readonly byKey = new Map<string, Seen>();

  add(p: { character_id: string | null; name: string; clan: string | null; standing: string | null; titles?: readonly string[] }): string {
    const key = personKey(p.character_id, p.name);
    const had = this.byKey.get(key);
    if (!had) {
      this.byKey.set(key, { key, character_id: p.character_id, name: p.name.trim(), clan: p.clan, standing: p.standing ?? "active", titles: [...(p.titles ?? [])] });
      return key;
    }
    had.clan ??= p.clan;
    if (had.standing === "active" && p.standing && p.standing !== "active") had.standing = p.standing;
    for (const t of p.titles ?? []) if (!had.titles.includes(t)) had.titles.push(t);
    // A name written in more than one way shows as the first in plain order, capitals first, as on the bonds web.
    if (!had.character_id && p.name.trim() < had.name) had.name = p.name.trim();
    return key;
  }
}

const ALL_KINDS: ReadonlySet<BoonKind> = new Set(KINDS.map((k) => k.value));

/** Every tie the sources give, before the web's own filters, and everyone on them. */
export function allTies(sources: Sources, endedBonds: boolean): { people: Map<string, Seen>; ties: Tie[] } {
  const people = new People();
  const ties: Tie[] = [];

  if (sources.boons) {
    const { nodes, links } = sources.boons;
    const keys = new Map(nodes.map((n) => [n.who.key, people.add({ ...n.who, standing: n.who.standing ?? "active" })]));
    // The boons network's own shaping, every kind shown, weighed with the troupe's weights.
    const shown = network(nodes, links, { clan: null, sect: null, court: false, kinds: ALL_KINDS, minWeight: 0 }, weightsOf(sources.boons));
    for (const l of shown.links) {
      const from = keys.get(l.debtor);
      const to = keys.get(l.creditor);
      if (!from || !to) continue;
      ties.push({ key: `boons:${from}>${to}`, layer: "boons", from, to, open: true, count: l.count, weight: l.shown, kind: l.kind, kinds: l.kinds });
    }
  }

  if (sources.bonds) {
    const keys = new Map(sources.bonds.people.map((p) => [p.key, people.add(p)]));
    // The bonds web's own shaping: everyone, every level, ended bonds as asked.
    const web = bondWeb(sources.bonds, { who: "everyone", full: false, ended: endedBonds, clan: null, titled: false });
    for (const l of web.links) {
      const from = keys.get(l.thrall);
      const to = keys.get(l.regnant);
      if (!from || !to) continue;
      ties.push({ key: `bonds:${l.id}`, layer: "bonds", from, to, open: l.open, level: l.level, status: l.status, fadesOn: l.fades_on });
    }
  }

  if (sources.sires) {
    const nodes = sources.sires.nodes;
    const keys = new Map(
      nodes.map((n) => [n.key, people.add({ character_id: n.character_id, name: n.name, clan: n.clan, standing: n.retired ? (n.left_reason ?? "retired") : "active" })]),
    );
    for (const n of nodes) {
      if (!n.sire_key) continue;
      const from = keys.get(n.sire_key);
      const to = keys.get(n.key);
      if (!from || !to || from === to) continue;
      ties.push({ key: `sires:${from}>${to}`, layer: "sires", from, to, open: true });
    }
  }

  return { people: people.byKey, ties };
}

/** The web as filtered: the ties that pass, the people at their ends, and what each person's shown ties add up to. */
export function obligationWeb(sources: Sources, filters: Filters): ObligationWeb {
  const { people, ties } = allTies(sources, filters.endedBonds);
  const passes = (key: string, test: (p: Seen) => boolean) => {
    const p = people.get(key);
    return !!p && test(p);
  };
  const kept = ties.filter((t) => {
    if (!filters.layers.has(t.layer)) return false;
    if (t.layer === "boons" && (t.weight ?? 0) < filters.boonMinimum) return false;
    const sides = [t.from, t.to];
    if (filters.who === "active" && !sides.every((k) => passes(k, (p) => p.standing === "active"))) return false;
    if (filters.clan !== null && !sides.some((k) => passes(k, (p) => clanKey(p.clan) === filters.clan))) return false;
    if (filters.titled && !sides.some((k) => passes(k, (p) => p.titles.length > 0))) return false;
    return true;
  });
  const shown = new Map<string, Person>();
  const person = (key: string) => {
    let p = shown.get(key);
    if (!p) {
      p = { ...people.get(key)!, titles: [...people.get(key)!.titles], owes: 0, owed: 0, thralls: 0, boundTo: 0, childer: 0, sire: null };
      shown.set(key, p);
    }
    return p;
  };
  for (const t of kept) {
    const from = person(t.from);
    const to = person(t.to);
    if (t.layer === "boons") {
      from.owes += t.weight ?? 0;
      to.owed += t.weight ?? 0;
    } else if (t.layer === "bonds" && t.open) {
      to.thralls += 1;
      from.boundTo += 1;
    } else if (t.layer === "sires") {
      from.childer += 1;
      to.sire = from.name;
    }
  }
  return { people: [...shown.values()].sort((a, b) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key)), ties: kept };
}

/** Owed less owing: above nought, others owe them more. */
export const net = (p: Pick<Person, "owes" | "owed">) => round(p.owed - p.owes);

const round = (n: number) => Math.round(n * 100) / 100;

/** How many ties of each layer touch someone, for sizing their dot. */
export function tiesOf(web: ObligationWeb, key: string): Tie[] {
  return web.ties.filter((t) => t.from === key || t.to === key);
}

/** Every tie someone has, in words, for the tooltip: one line per layer. */
export function summary(web: ObligationWeb, p: Person): { label: string; value: string }[] {
  const mine = tiesOf(web, p.key);
  const rows: { label: string; value: string }[] = [];
  const boons = mine.filter((t) => t.layer === "boons");
  if (boons.length) {
    const owing = boons.filter((t) => t.from === p.key).reduce((n, t) => n + (t.count ?? 0), 0);
    const owedTo = boons.filter((t) => t.to === p.key).reduce((n, t) => n + (t.count ?? 0), 0);
    rows.push({ label: "boons", value: `owes ${owing} (${round(p.owes)}), is owed ${owedTo} (${round(p.owed)})` });
  }
  if (mine.some((t) => t.layer === "bonds")) rows.push({ label: "blood bonds", value: `${p.thralls} ${p.thralls === 1 ? "thrall" : "thralls"}, bound to ${p.boundTo}` });
  if (p.sire || p.childer) rows.push({ label: "sire line", value: [p.sire ? `sire ${p.sire}` : "", p.childer ? `${p.childer} ${p.childer === 1 ? "childe" : "childer"}` : ""].filter(Boolean).join(", ") });
  return rows;
}

/** The clans of everyone in the sources, for the clan filter. */
export function webClans(sources: Sources): string[] {
  const { people } = allTies(sources, true);
  return [...new Set([...people.values()].map((p) => clanKey(p.clan)))].sort((a, b) => a.localeCompare(b));
}
