/**
 * Gossip and Insider Trading and Word on the Street, filled from the influence log,
 * and discovery blocks (backend: horatio.influence_lookups). A lookup covers all the
 * character's specialisations of its type, and each answer taking it in the cycle
 * adds one to its strength: an entry blocked N times needs strength N + 1.
 */
import type { InfluenceEntryOut, LookupOut, OwnEntryOut } from "./api/types";
import type { Dates } from "./dates";
import { TYPE_NAMES } from "./influence";

/** What the player sees beside a lookup on the downtime form. */
export const LOOKUP_NOTE = "Covers all your specialisations; more actions find better-hidden things.";

/** The level the lookups are, in each type's list. */
export const LOOKUP_LEVEL = 2;

export const DISCOVERY_BLOCK = "discovery_block";

/** "A, B and C". */
function listed(items: string[]): string {
  return items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/** One entry found, as players read it: when, where, what and why, never who. */
export function foundLine(found: LookupOut["found"][number], dates: Dates): string {
  const parts = [dates.date(found.happened_at), found.specialization, found.action, found.purpose].filter(Boolean);
  const times = found.times > 1 ? ` (this action is logged ${found.times} times)` : "";
  return `- ${parts.join(", ")}${times} (${found.short_id})`;
}

/** The result, for the last of the character's answers taking the lookup. */
export function resultText(lookup: LookupOut, dates: Dates): string {
  const since = dates.date(lookup.window.since);
  const type = TYPE_NAMES[lookup.type];
  if (!lookup.specializations.length) return `${lookup.action_name} covers your ${type} specialisations, and you have none, so it finds nothing.`;
  const head = `${lookup.action_name}, strength ${lookup.strength}, in ${listed(lookup.specializations)}`;
  if (!lookup.found.length) return `${head}: nothing found since ${since}.`;
  return [`${head}, since ${since}:`, ...lookup.found.map((f) => foundLine(f, dates))].join("\n");
}

/** What the character's other answers taking the lookup say. */
export function combinedText(lookup: LookupOut): string {
  return `Combined with your other ${lookup.action_name} actions: strength ${lookup.strength}, results below.`;
}

/** Each answer's response: the result on the last, in the form's order, and "Combined with…" on the others. */
export function lookupTexts(lookup: LookupOut, dates: Dates): Record<string, string> {
  const last = lookup.answers.at(-1)?.response_id;
  return Object.fromEntries(lookup.answers.map((a) => [a.response_id, a.response_id === last ? resultText(lookup, dates) : combinedText(lookup)]));
}

type Entry = Pick<OwnEntryOut, "short_id" | "happened_at" | "type" | "specialization" | "action" | "purpose">;

function what(entry: Entry): string[] {
  return [`${TYPE_NAMES[entry.type]}${entry.specialization ? `, ${entry.specialization}` : ""}`, entry.action, entry.purpose].filter(Boolean);
}

/** An entry to block, as a player picks one of their own. */
export function ownEntryLabel(entry: Entry, dates: Dates): string {
  return [entry.short_id, dates.date(entry.happened_at), ...what(entry)].join(" · ");
}

/** An entry to block, as staff choose one: with who took it. */
export function entryLabel(entry: InfluenceEntryOut, dates: Dates): string {
  return [entry.short_id, dates.date(entry.happened_at), entry.name, ...what(entry)].join(" · ");
}
