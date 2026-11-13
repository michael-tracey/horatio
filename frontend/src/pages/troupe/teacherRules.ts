/**
 * A troupe's teacher rules, as the form under Customise › House rules › Teachers makes
 * them: which traits, for whom (the house checks' blocks, horatio.rules.house_checks),
 * when, what the teacher must hold, and what learning costs besides; turned into
 * what the server takes (horatio.rules.teachers), and back again to change one.
 */

import type { CatalogueOut, TeacherRuleBriefOut, TeacherRuleIn, TeacherRuleOut } from "../../api/types";
import { BuildProblem, fromCondition, toCondition, type CondBlock } from "./ownChecks";

/** Which traits of the category: some by name, those whose names start with a prefix, or all. */
export type WhichHow = "traits" | "prefix" | "all";

export type Draft = {
  splat: string;
  category: string;
  how: WhichHow;
  names: string[];
  prefix: string;
  /** For everyone, or only for characters the blocks hold for. */
  everyone: boolean;
  blocks: CondBlock[];
  /** Always, or only once creation is finished. */
  always: boolean;
  holds: "same" | "rating";
  rating: number;
  actions: number;
  willpower: number;
  games: number;
};

export const EMPTY: Draft = {
  splat: "vampire",
  category: "skills",
  how: "traits",
  names: [],
  prefix: "",
  everyone: true,
  blocks: [],
  always: false,
  holds: "same",
  rating: 1,
  actions: 0,
  willpower: 0,
  games: 2,
};

/** Rules troupes asked for (issue #440), to start one from. */
export const EXAMPLES: { label: string; draft: Draft }[] = [
  {
    label: "Lore specialisations after creation, with a downtime action",
    draft: { ...EMPTY, category: "lore_specializations", how: "all", actions: 1 },
  },
  {
    label: "Lore dots, from a teacher with at least the rating",
    draft: { ...EMPTY, names: ["Lore"], always: true },
  },
  {
    label: "Elders' Computer, Drive and Firearms, for a Willpower back after 2 games",
    draft: {
      ...EMPTY,
      names: ["Computer", "Drive", "Firearms"],
      everyone: false,
      blocks: [{ type: "generation_gte", value: 3 }],
      willpower: 1,
      games: 2,
    },
  },
];

/** The draft as the server takes it, or why it cannot be yet. */
export function toBody(draft: Draft): { body: TeacherRuleIn } | { problem: string } {
  if (draft.how === "traits" && !draft.names.length) return { problem: "Choose at least one trait." };
  const prefix = draft.prefix.trim();
  if (draft.how === "prefix" && !prefix) return { problem: "Write the start of the names." };
  let condition: Record<string, unknown> | null = null;
  if (!draft.everyone) {
    try {
      condition = toCondition(draft.blocks);
    } catch (e) {
      if (e instanceof BuildProblem) return { problem: e.message };
      throw e;
    }
  }
  if (draft.willpower > 0 && draft.games < 1) return { problem: "Say after how many games the Willpower returns." };
  return {
    body: {
      splat: draft.splat,
      category: draft.category,
      names: draft.how === "traits" ? draft.names : [],
      name_prefix: draft.how === "prefix" ? prefix : null,
      condition,
      always: draft.always,
      holds: draft.holds,
      rating: draft.holds === "rating" ? draft.rating : null,
      actions: draft.actions,
      willpower: draft.willpower,
      games: draft.willpower > 0 ? draft.games : 0,
    },
  };
}

/** A saved rule as a draft, to change it; null if the form has no blocks for its condition. */
export function draftOf(rule: TeacherRuleOut): Draft | null {
  let blocks: CondBlock[] = [];
  if (rule.condition) {
    try {
      blocks = fromCondition(rule.condition);
    } catch (e) {
      if (e instanceof BuildProblem) return null;
      throw e;
    }
  }
  const names = rule.names ?? [];
  return {
    splat: rule.splat ?? "vampire",
    category: rule.category,
    how: names.length ? "traits" : rule.name_prefix ? "prefix" : "all",
    names,
    prefix: rule.name_prefix ?? "",
    everyone: !rule.condition,
    blocks,
    always: rule.always ?? false,
    holds: rule.holds ?? "same",
    rating: rule.rating ?? 1,
    actions: rule.actions ?? 0,
    willpower: rule.willpower ?? 0,
    games: rule.games || 2,
  };
}

/** The kinds of trait a rule can be about: bought in dots, not worked out from the
 * sheet, and not merits or flaws (asked of staff already once accepted). */
export function teachable(catalogue: CatalogueOut): CatalogueOut["categories"] {
  return catalogue.categories.filter(
    (c) => c.rated && !c.derived && c.key !== "merits" && c.key !== "flaws" && catalogue.traits.some((t) => t.category === c.key),
  );
}

/** The highest rating a teacher could be asked to hold in a category. */
export function topOf(catalogue: CatalogueOut, category: string): number {
  return Math.min(catalogue.categories.find((c) => c.key === category)?.max_rating ?? 5, 10);
}

/** Whether a rule that applies to the character is about this trait. */
export function ruleAbout(rule: Pick<TeacherRuleBriefOut, "category" | "names" | "name_prefix">, category: string, name: string): boolean {
  if (rule.category !== category) return false;
  if (rule.names.length && !rule.names.includes(name)) return false;
  return !rule.name_prefix || name.startsWith(rule.name_prefix);
}

/** What the teacher's Willpower costs, in words: "1 Willpower, back after 2 games". */
export function willpowerText(willpower: number, games: number): string {
  return `${willpower} Willpower, back after ${games} ${games === 1 ? "game" : "games"}`;
}
