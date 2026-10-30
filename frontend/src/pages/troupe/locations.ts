import type { LocationOut, LocationSuggestion } from "../../api/types";

export type Kind = LocationOut["kind"];

const KINDS: Record<Kind, string> = { standard: "Standard", prestige: "Prestige", iconic: "Iconic", haven: "Haven" };

/** "Prestige 5", or "Haven 2". */
export function typeText(location: Pick<LocationOut, "kind" | "rating">): string {
  return `${KINDS[location.kind]} ${location.rating}`;
}

/** Who controls it, in a few words. */
export function controlText(location: Pick<LocationOut, "control" | "controller" | "joint">): string {
  if (location.control === "uncontrollable") return "Uncontrollable";
  if (!location.controller) return "Uncontrolled";
  return location.joint ? `${location.controller.name} and ${location.joint.name}` : location.controller.name;
}

/** A quality as held: "Laboratory (Chemistry)". */
export function qualityText(q: { name: string; detail: string }): string {
  return q.detail ? `${q.name} (${q.detail})` : q.name;
}

/** The qualities, with one held more than once counted: "Profitable ×2, Size". */
export function qualitiesText(qualities: { name: string; detail: string }[]): string {
  const counts = new Map<string, number>();
  for (const q of qualities) counts.set(qualityText(q), (counts.get(qualityText(q)) ?? 0) + 1);
  return [...counts].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(", ");
}

export function influenceText(location: Pick<LocationOut, "influence_type" | "influence_area">): string {
  if (!location.influence_type) return "";
  const type = location.influence_type === "elite" ? "Elite" : "Underworld";
  return location.influence_area ? `${location.influence_area} (${type})` : type;
}

export type Filters = {
  query: string;
  controller: string;
  kind: string;
  quality: string;
  influence: string;
  block: string;
  locked: "" | "locked" | "open";
  negatives: "" | "any" | "secret" | "none";
};

export const NO_FILTERS: Filters = { query: "", controller: "", kind: "", quality: "", influence: "", block: "", locked: "", negatives: "" };

/** The key a location's controller is filtered by: a character's id, a name, or how it is held. */
export function controllerKey(location: Pick<LocationOut, "control" | "controller">): string {
  if (location.control === "uncontrollable") return "uncontrollable";
  if (!location.controller) return "none";
  return location.controller.id ? `c:${location.controller.id}` : `n:${location.controller.name}`;
}

/** The locations the filters and search let through. */
export function filtered(locations: LocationOut[], f: Filters): LocationOut[] {
  const q = f.query.trim().toLowerCase();
  return locations.filter(
    (l) =>
      (!q || `${l.name} ${l.address}`.toLowerCase().includes(q)) &&
      (!f.controller || controllerKey(l) === f.controller || (l.joint?.id && `c:${l.joint.id}` === f.controller)) &&
      (!f.kind || l.kind === f.kind) &&
      (!f.quality || l.qualities.some((x) => x.name === f.quality)) &&
      (!f.influence || influenceText(l) === f.influence) &&
      (!f.block || l.feeding_block === f.block) &&
      (!f.locked || (f.locked === "locked") === l.locked) &&
      (!f.negatives ||
        (f.negatives === "none" ? l.negatives.length === 0 : f.negatives === "secret" ? l.negatives.some((n) => n.secret) : l.negatives.length > 0)),
  );
}

/** The distinct values of something on the list, sorted, for a filter's options. */
export function distinct(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

type Suggestion = Partial<LocationSuggestion>;

/** A suggested requirement with every field, as the API takes it. */
export function fullSuggestion(s: Suggestion): LocationSuggestion {
  return { trait: "", traits: [], power: "", levels: [], detail: "", expend: false, alternative: "", text: "", ...s };
}

/** A suggested requirement as the troupe's sheet writes it: "Crafts [2,3,4]", "expend Resources [4,5]". */
export function suggestionText(s: Suggestion): string {
  if (s.text) return s.text;
  const what = s.power || (s.traits?.length ? s.traits.join(" or ") : s.trait);
  const parts = [s.expend ? `expend ${what}` : what];
  if (s.detail) parts.push(`(${s.detail})`);
  if (s.levels?.length) parts.push(`[${s.levels.join(",")}]`);
  const text = parts.join(" ");
  return s.alternative ? `${text}, or ${s.alternative}` : text;
}

/**
 * Suggested requirements typed one to a line, as the troupe's sheet writes them:
 * "Crafts [2,3,4]" is a trait at levels by the location's rating; anything without
 * levels in brackets stays words.
 */
export function parseSuggestions(text: string): Suggestion[] {
  const found: Suggestion[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = /^(.+?)\s*\[([\d,\s]+)\]$/.exec(line);
    const levels = m ? m[2]!.split(",").map((n) => Number(n.trim())).filter((n) => n >= 1 && n <= 5) : [];
    if (!m || !levels.length) {
      found.push({ text: line });
      continue;
    }
    const trait = m[1]!.trim();
    const expend = /^expend\s+/i.test(trait);
    found.push({ trait: trait.replace(/^expend\s+/i, ""), levels: [...levels].sort((a, b) => a - b), ...(expend ? { expend } : {}) });
  }
  return found;
}

/** Suggested requirements back as lines, for editing. */
export function suggestionLines(suggested: Suggestion[]): string {
  return suggested.map(suggestionText).join("\n");
}

/** How many qualities it has of how many: "10 of 10 qualities". */
export function countText(location: Pick<LocationOut, "kind" | "quality_count" | "most_qualities">): string {
  if (location.kind === "haven") return "";
  return `${location.quality_count} of ${location.most_qualities} ${location.most_qualities === 1 ? "quality" : "qualities"}`;
}
