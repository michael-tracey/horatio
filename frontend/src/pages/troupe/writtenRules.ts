/**
 * A troupe's written house rules (#434): rules in words alone, read by section. The
 * server gives them in reading order; these group them and name their places.
 */
import type { WrittenRuleOut } from "../../api/types";

/** What a rule with no section is read under. */
export const NO_SECTION = "General";

/** A section's heading. */
export const sectionLabel = (section: string) => section || NO_SECTION;

/** The rules under each section, in the order given. */
export function bySection<T extends Pick<WrittenRuleOut, "section">>(rules: T[]): { section: string; rules: T[] }[] {
  const found: { section: string; rules: T[] }[] = [];
  for (const rule of rules) {
    const last = found[found.length - 1];
    if (last?.section === rule.section) last.rules.push(rule);
    else found.push({ section: rule.section, rules: [rule] });
  }
  return found;
}

/** The id of a rule's place on the page, to link to. */
export const ruleAnchor = (id: string) => `written-rule-${id}`;

/** Where a troupe's players read a rule: its House rules tab, at the rule. */
export const ruleLink = (troupeId: string, id: string) => `/troupes/${troupeId}/house-rules#${ruleAnchor(id)}`;

/** The sections in use, for staff to pick from when adding one. */
export function sectionsInUse(rules: Pick<WrittenRuleOut, "section">[]): string[] {
  return [...new Set(rules.map((r) => r.section).filter(Boolean))];
}

/** What a rule's search looks in, in lower case. */
export const searchText = (rule: WrittenRuleOut) =>
  [rule.title, rule.section, rule.body, rule.trait?.name].filter(Boolean).join(" ").toLowerCase();
