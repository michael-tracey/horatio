import type { StatusSourceOut } from "../../api/types";

/** "A", "A and B", "A, B and C". */
function list(names: string[]): string {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
}

/** A title as a status's source: "Harpy (or Master Harpy)", "Seneschal (while the Prince is absent)". */
function titleText(g: StatusSourceOut): string {
  const more = [...(g.aliases.length ? [`or ${g.aliases.join(" or ")}`] : []), ...(g.condition ? [g.condition] : []), ...(g.house ? ["ours"] : [])];
  return more.length ? `${g.name} (${more.join("; ")})` : g.name;
}

const KINDS: [StatusSourceOut["kind"], string, string][] = [
  ["title", "the title", "the titles"],
  ["social_age", "the social age", "the social ages"],
  ["faction", "the faction", "the factions"],
  ["merit", "the merit", "the merits"],
];

/**
 * What gives a status in the troupe, in a line: "Given here by the titles Harpy (or
 * Master Harpy) and Keeper of Elysium; the social age Elder." Null when nothing does:
 * fleeting and negative status is given by people, not by a title.
 */
export function givenByText(given: StatusSourceOut[]): string | null {
  const parts = KINDS.flatMap(([kind, one, many]) => {
    const names = given.filter((g) => g.kind === kind).map((g) => (kind === "title" ? titleText(g) : g.name));
    return names.length ? [`${names.length > 1 ? many : one} ${list(names)}`] : [];
  });
  return parts.length ? `Given here by ${parts.join("; ")}.` : null;
}

/** The kinds of status, what each is, and where the book says so (MET: VTM). */
export const STATUS_TYPES: { type: string; meaning: string; page: string }[] = [
  { type: "Accepted", meaning: "Membership of the sect, not a status: it never counts toward a total, and can't be spent.", page: "310" },
  { type: "Abiding", meaning: "From a position, such as a title: it comes back at the start of each game while the position is held.", page: "311" },
  { type: "Innate", meaning: "From something the character is, usually a merit or flaw: it comes back at the start of each game.", page: "312" },
  { type: "Fleeting", meaning: "Earned by deeds or given by a patron: once spent, it is gone.", page: "312" },
  { type: "Negative", meaning: "A punishment: it can't be spent, and lasts until it is removed or its time runs out.", page: "311" },
];
