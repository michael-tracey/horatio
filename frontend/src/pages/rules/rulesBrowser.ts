/**
 * The rules browser (issue #422): the catalogue, its powers and its rules about
 * each trait, made into one list to search and filter on the page, so typing asks
 * nothing of the server.
 */
import type { DisciplinePowerOut, NotAllowedOut, PriceOut, RarityOut, RulesBrowserOut, TraitCheckOut, TraitOut, WrittenRuleOut } from "../../api/types";
import { searchText } from "../troupe/writtenRules";

/** A part of the browser, and the catalogue categories it shows, in order. */
export type Section = { key: string; label: string; categories: string[] };

export const SECTIONS: Section[] = [
  { key: "merits", label: "Merits", categories: ["merits"] },
  { key: "flaws", label: "Flaws", categories: ["flaws"] },
  { key: "disciplines", label: "Disciplines and powers", categories: ["disciplines", "elder_disciplines", "luminary_disciplines"] },
  { key: "techniques", label: "Techniques", categories: ["techniques"] },
  { key: "rituals", label: "Rituals", categories: ["rituals"] },
  { key: "backgrounds", label: "Backgrounds", categories: ["backgrounds"] },
  { key: "skills", label: "Skills", categories: ["skills"] },
  { key: "clans", label: "Clans", categories: ["clan"] },
  { key: "paths", label: "Paths", categories: ["paths"] },
];

/** The troupe's written house rules (#434): a part of their own, before the catalogue's. */
export const WRITTEN: Section = { key: "written", label: "Written rules", categories: ["written"] };

/** The section a catalogue category is browsed in, if it is. */
export function sectionOf(category: string): Section | undefined {
  return SECTIONS.find((s) => s.categories.includes(category));
}

/**
 * The browser's address for the first of `categories` it shows, as played in
 * `troupeId` (the book's rules without one), for `splat`'s rules; null if it
 * shows none of them.
 */
export function rulesLink(categories: string[], troupeId?: string | null, splat = "vampire"): string | null {
  const section = categories.map(sectionOf).find((s) => s !== undefined);
  if (!section) return null;
  const params = new URLSearchParams({ category: section.key });
  if (troupeId) params.set("troupe", troupeId);
  if (splat !== "vampire") params.set("splat", splat);
  return `/rules?${params}`;
}

/** One thing to read about: a trait from the catalogue, or a power of a discipline. */
export type Entry = {
  key: string;
  section: string;
  /** Its catalogue category; a power's is its discipline's, "disciplines". */
  category: string;
  name: string;
  /** "3 points", "Level 2", or for a power its discipline and dot: "Presence 5". */
  rating: string | null;
  /** The number the rating filter goes by: points, a level or a power's dot. */
  value: number | null;
  summary: string | null;
  page: string | null;
  /** Who it is for: a clan or bloodline ("Toreador"), as the catalogue says. */
  requirement: string | null;
  /** The clans the clan filter finds it under: those it is for, or in-clan for. */
  clans: string[];
  /** The checks about it alone. */
  checks: TraitCheckOut[];
  /** The prices naming it alone. */
  prices: PriceOut[];
  /** The catalogue's entry; null for a power. */
  trait: TraitOut | null;
  /** Barred by the troupe's house rules. */
  barred: NotAllowedOut | null;
  /** For a clan or bloodline: how rare it is. */
  rarity: RarityOut | null;
  /** For one of the troupe's written rules: the rule. */
  written?: WrittenRuleOut;
  /** What a search looks in, in lower case. */
  text: string;
};

/** A clan's own name, without its bloodline: "Toreador" for "Toreador: Volgirre". */
export const family = (clan: string) => clan.split(":")[0]!.trim();

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function ratingOf(trait: TraitOut): string | null {
  const n = trait.fixed_rating;
  if (n == null) return null;
  if (trait.category === "merits" || trait.category === "flaws") return plural(n, "point");
  return `Level ${n}`;
}

/**
 * Every entry the browser can show, in reading order: the troupe's written rules
 * as it orders them, then by section, category and name, each discipline followed
 * by its powers by dot.
 */
export function entries(data: RulesBrowserOut): Entry[] {
  const traits = data.catalogue.traits;
  const order = new Map(SECTIONS.flatMap((s) => s.categories).map((c, n) => [c, n]));
  const shown = traits.filter((t) => order.has(t.category));
  const checks = group(data.requirements.filter((r) => r.trait), (r) => `${r.category}/${r.trait}`);
  const prices = group(data.prices.filter((p) => p.trait), (p) => `${p.category}/${p.trait}`);
  const barred = new Map(data.not_allowed.map((b) => [`${b.category}/${b.name}`, b]));
  const rarity = new Map(data.rarities.map((r) => [r.clan, r]));
  const powers = group(data.powers, (p) => p.discipline);
  // Which clans have each discipline in-clan: the clans themselves, not their bloodlines.
  const inClanFor = new Map<string, string[]>();
  for (const clan of traits.filter((t) => t.category === "clan" && !t.name.includes(":"))) {
    for (const d of clan.in_clan ?? []) inClanFor.set(d, [...(inClanFor.get(d) ?? []), clan.name]);
  }
  const sorted = [...shown].sort((a, b) => order.get(a.category)! - order.get(b.category)! || a.name.localeCompare(b.name));
  const found: Entry[] = (data.written_rules ?? []).map(writtenEntry);
  for (const t of sorted) {
    const key = `${t.category}/${t.name}`;
    const section = sectionOf(t.category)!.key;
    // An elder or luminary power belongs to the discipline before its colon.
    const discipline = t.category === "disciplines" ? t.name : family(t.name);
    const clans =
      t.category === "clan"
        ? [family(t.name)]
        : section === "disciplines"
          ? (inClanFor.get(t.name) ?? inClanFor.get(discipline) ?? [])
          : t.requirement
            ? [family(t.requirement)]
            : [];
    found.push({
      key,
      section,
      category: t.category,
      name: t.name,
      rating: ratingOf(t),
      value: t.fixed_rating ?? null,
      summary: t.description || t.house?.summary || null,
      page: t.page_reference ?? null,
      requirement: t.requirement ?? null,
      clans,
      checks: checks.get(key) ?? [],
      prices: prices.get(key) ?? [],
      trait: t,
      barred: barred.get(key) ?? null,
      rarity: t.category === "clan" ? (rarity.get(t.name) ?? rarity.get(family(t.name)) ?? null) : null,
      text: [t.name, t.description, t.requirement, t.kind, t.house?.summary, t.house_rule].filter(Boolean).join(" ").toLowerCase(),
    });
    if (t.category === "disciplines") found.push(...(powers.get(t.name) ?? []).map((p) => powerEntry(p, t, clans)));
  }
  return found;
}

function writtenEntry(rule: WrittenRuleOut): Entry {
  return {
    key: `written/${rule.id}`,
    section: WRITTEN.key,
    category: "written",
    name: rule.title,
    rating: null,
    value: null,
    summary: null,
    page: rule.page ?? null,
    requirement: null,
    clans: [],
    checks: [],
    prices: [],
    trait: null,
    barred: null,
    rarity: null,
    written: rule,
    text: searchText(rule),
  };
}

function powerEntry(power: DisciplinePowerOut, discipline: TraitOut, clans: string[]): Entry {
  return {
    key: `power/${power.discipline}/${power.name}`,
    section: "disciplines",
    category: "disciplines",
    name: power.name,
    rating: `${power.discipline} ${power.level}`,
    value: power.level,
    summary: power.note,
    page: discipline.page_reference ?? null,
    requirement: null,
    clans,
    checks: [],
    prices: [],
    trait: null,
    barred: null,
    rarity: null,
    text: `${power.name} ${power.discipline} ${power.note}`.toLowerCase(),
  };
}

function group<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const found = new Map<string, T[]>();
  for (const item of items) found.set(key(item), [...(found.get(key(item)) ?? []), item]);
  return found;
}

/** What the page is narrowed to. Empty means any. */
export type Filters = {
  section: string;
  query: string;
  clan: string;
  rating: number | null;
  /** Show what the troupe does not allow, marked so. */
  barred: boolean;
};

/** Whether an entry holds every word searched for, in its name, summary or who it is for. */
export function matches(entry: Entry, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return words.every((w) => entry.text.includes(w));
}

/** The entries the filters leave, in order. */
export function applyFilters(all: Entry[], f: Filters): Entry[] {
  return all.filter(
    (e) =>
      (!f.section || e.section === f.section) &&
      (f.barred || !e.barred) &&
      (!f.clan || e.clans.includes(f.clan)) &&
      (f.rating == null || e.value === f.rating) &&
      matches(e, f.query),
  );
}

/** How many entries the other filters leave in each section, for its chip. */
export function sectionCounts(all: Entry[], f: Filters): Map<string, number> {
  const counts = new Map<string, number>();
  for (const e of applyFilters(all, { ...f, section: "" })) counts.set(e.section, (counts.get(e.section) ?? 0) + 1);
  return counts;
}

/** The ratings the section's entries have, for the rating filter, lowest first. */
export function ratingChoices(all: Entry[], section: string): number[] {
  return [...new Set(all.filter((e) => e.section === section && e.value != null).map((e) => e.value!))].sort((a, b) => a - b);
}

/** What the rating filter is called in a section. */
export function ratingLabel(section: string): string {
  if (section === "merits" || section === "flaws") return "Points";
  if (section === "rituals" || section === "disciplines") return "Level";
  return "Rating";
}

/** The clans to filter by: each clan, not its bloodlines, which it finds too. */
export function clanChoices(data: RulesBrowserOut): string[] {
  return data.catalogue.traits
    .filter((t) => t.category === "clan" && !t.name.includes(":"))
    .map((t) => t.name)
    .sort();
}

/**
 * The checks every trait of a category is held to, rather than one trait: a
 * category's own and those for names starting a certain way (Thaumaturgy rituals).
 */
export function generalChecks(data: RulesBrowserOut, category: string): TraitCheckOut[] {
  return data.requirements.filter((r) => r.category === category && !r.trait);
}

/** The prices of a whole category, under each condition. */
export function categoryPrices(data: RulesBrowserOut, category: string): PriceOut[] {
  return data.prices.filter((p) => p.category === category && !p.trait);
}

/**
 * The checks to list under an entry. A clan-only merit's check says no more than
 * the clan beside its name, so it is left out, unless the troupe changed it.
 */
export function shownChecks(entry: Entry): TraitCheckOut[] {
  return entry.checks.filter((c) => !(c.key.endsWith("/requirement") && entry.requirement && !c.house));
}
