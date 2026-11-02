/**
 * A troupe's own checks, as the builder on the Checks page makes them: a subject
 * picked from the catalogue and a condition built from blocks, turned into the
 * condition JSON the server runs through the book's engine (horatio.rules.checks,
 * checked by horatio.rules.house_checks), and back again to edit one.
 */

import type { CatalogueOut, OwnCheckIn, OwnCheckOut } from "../../api/types";

/** One block of a condition. Blocks side by side must all hold. */
export type CondBlock =
  | { type: "clan"; names: string[] }
  | { type: "clan_family"; names: string[] }
  | { type: "has"; category: string; name: string; rating: number | null }
  | { type: "generation_gte"; value: number }
  | { type: "generation_lte"; value: number }
  | { type: "finished" }
  | { type: "copies"; value: number }
  | { type: "self"; names: string[] }
  | { type: "not"; blocks: CondBlock[] }
  | { type: "any_of"; blocks: CondBlock[] }
  | { type: "all_of"; blocks: CondBlock[] };

export type CondType = CondBlock["type"];
export type Condition = Record<string, unknown>;

export const COND_TYPES: { type: CondType; label: string }[] = [
  { type: "clan", label: "Clan is one of…" },
  { type: "clan_family", label: "Clan or its bloodlines…" },
  { type: "has", label: "Holds a trait (at a rating)…" },
  { type: "generation_gte", label: "Generation at least…" },
  { type: "generation_lte", label: "Generation at most…" },
  { type: "finished", label: "Character creation is finished" },
  { type: "copies", label: "Holds this trait more than once" },
  { type: "self", label: "This trait is one of…" },
  { type: "not", label: "Not…" },
  { type: "any_of", label: "Any of…" },
  { type: "all_of", label: "All of…" },
];

export const condLabel = (type: CondType) => COND_TYPES.find((t) => t.type === type)?.label ?? type;

export function newCondBlock(type: CondType): CondBlock {
  switch (type) {
    case "clan":
    case "clan_family":
    case "self":
      return { type, names: [] };
    case "has":
      return { type, category: "backgrounds", name: "", rating: null };
    case "generation_gte":
    case "generation_lte":
      return { type, value: 4 };
    case "finished":
      return { type };
    case "copies":
      return { type, value: 2 };
    case "not":
    case "any_of":
    case "all_of":
      return { type, blocks: [] };
  }
}

/** Why the blocks cannot make a condition yet, in words for the form. */
export class BuildProblem extends Error {}

type Trait = { category: string; name: string; rating?: number };

function trait(block: Extract<CondBlock, { type: "has" }>): Trait {
  if (!block.category || !block.name) throw new BuildProblem("Choose the trait it holds.");
  return block.rating ? { category: block.category, name: block.name, rating: block.rating } : { category: block.category, name: block.name };
}

/** Put one block's key into a condition table, beside those already there. */
function put(into: Condition, key: string, value: unknown, type: CondType) {
  if (key === "has" || key === "has_all") {
    const held = [...((into.has_all as Trait[] | undefined) ?? []), ...(into.has ? [into.has as Trait] : [])];
    const adding = key === "has" ? [value as Trait] : (value as Trait[]);
    if (!held.length && key === "has") {
      into.has = value;
      return;
    }
    delete into.has;
    into.has_all = [...held, ...adding];
    return;
  }
  if (key === "generation") {
    const before = (into.generation as Record<string, number> | undefined) ?? {};
    const adding = value as Record<string, number>;
    if (Object.keys(adding).some((op) => op in before)) throw new BuildProblem(`“${condLabel(type)}” is used twice side by side.`);
    into.generation = { ...before, ...adding };
    return;
  }
  if (key === "not" && into.not) {
    // Not A and not B: neither of them.
    into.not = { any_of: [into.not, value] };
    return;
  }
  if (key in into) throw new BuildProblem(`“${condLabel(type)}” is used twice side by side; put one of them under “Any of” or “Not”.`);
  into[key] = value;
}

function names(block: { names: string[] }, what: string): string[] {
  if (!block.names.length) throw new BuildProblem(`Choose at least one ${what}.`);
  return block.names;
}

/** Blocks side by side, all of which must hold, as one condition table. */
export function toCondition(blocks: CondBlock[]): Condition {
  if (!blocks.length) throw new BuildProblem("Add at least one block to the condition.");
  const out: Condition = {};
  for (const b of blocks) {
    switch (b.type) {
      case "clan":
        put(out, "clan", names(b, "clan"), b.type);
        break;
      case "clan_family":
        put(out, "clan_family", names(b, "clan"), b.type);
        break;
      case "has":
        put(out, "has", trait(b), b.type);
        break;
      case "generation_gte":
        put(out, "generation", { gte: b.value }, b.type);
        break;
      case "generation_lte":
        put(out, "generation", { lte: b.value }, b.type);
        break;
      case "finished":
        put(out, "finished", true, b.type);
        break;
      case "copies":
        put(out, "copies", { gte: b.value }, b.type);
        break;
      case "self":
        put(out, "self", { names: names(b, "trait") }, b.type);
        break;
      case "not":
        if (!b.blocks.length) throw new BuildProblem("Put a block inside “Not”.");
        put(out, "not", toCondition(b.blocks), b.type);
        break;
      case "any_of":
        if (b.blocks.length < 2) throw new BuildProblem("“Any of” needs at least two blocks.");
        put(
          out,
          "any_of",
          b.blocks.map((c) => toCondition(c.type === "all_of" ? c.blocks : [c])),
          b.type,
        );
        break;
      case "all_of":
        for (const [key, value] of Object.entries(toCondition(b.blocks))) put(out, key, value, b.type);
        break;
    }
  }
  return out;
}

const isTable = (v: unknown): v is Condition => typeof v === "object" && v !== null && !Array.isArray(v);
const isNames = (v: unknown): v is string[] => Array.isArray(v) && v.every((n) => typeof n === "string");

function heldBlock(t: unknown): CondBlock {
  if (!isTable(t) || typeof t.category !== "string" || typeof t.name !== "string") throw new BuildProblem("The form cannot show this condition.");
  return { type: "has", category: t.category, name: t.name, rating: typeof t.rating === "number" ? t.rating : null };
}

/** A condition table as blocks, to edit it; throws if the form has no blocks for it. */
export function fromCondition(condition: unknown): CondBlock[] {
  if (!isTable(condition)) throw new BuildProblem("The form cannot show this condition.");
  const blocks: CondBlock[] = [];
  for (const [key, test] of Object.entries(condition)) {
    if ((key === "clan" || key === "clan_family") && isNames(test)) blocks.push({ type: key, names: test });
    else if (key === "has") blocks.push(heldBlock(test));
    else if (key === "has_all" && Array.isArray(test)) blocks.push(...test.map(heldBlock));
    else if (key === "generation" && isTable(test)) {
      for (const [op, value] of Object.entries(test)) {
        if ((op !== "gte" && op !== "lte") || typeof value !== "number") throw new BuildProblem("The form cannot show this condition.");
        blocks.push({ type: op === "gte" ? "generation_gte" : "generation_lte", value });
      }
    } else if (key === "finished" && typeof test === "boolean") blocks.push(test ? { type: "finished" } : { type: "not", blocks: [{ type: "finished" }] });
    else if (key === "copies" && isTable(test) && typeof test.gte === "number" && Object.keys(test).length === 1) blocks.push({ type: "copies", value: test.gte });
    else if (key === "self" && isTable(test) && isNames(test.names) && Object.keys(test).length === 1) blocks.push({ type: "self", names: test.names });
    else if (key === "not") blocks.push({ type: "not", blocks: fromCondition(test) });
    else if (key === "any_of" && Array.isArray(test))
      blocks.push({
        type: "any_of",
        blocks: test.map((c) => {
          const inner = fromCondition(c);
          return inner.length === 1 ? inner[0]! : { type: "all_of", blocks: inner };
        }),
      });
    else throw new BuildProblem("The form cannot show this condition.");
  }
  return blocks;
}

// --- the whole check ---------------------------------------------------------------

/** What a check is about, as the form picks it. */
export type SubjectHow = "trait" | "prefix" | "kind" | "all";

export type Draft = {
  splat: string;
  category: string;
  how: SubjectHow;
  /** The trait's name, the prefix or the type, as `how` says. */
  value: string;
  mode: "requires" | "forbids";
  blocks: CondBlock[];
  strength: OwnCheckIn["strength"];
  message: string;
  step: string;
};

export const EMPTY: Draft = {
  splat: "vampire",
  category: "merits",
  how: "trait",
  value: "",
  mode: "forbids",
  blocks: [],
  strength: "refuse",
  message: "",
  step: "",
};

export const STRENGTHS: { strength: OwnCheckIn["strength"]; label: string }[] = [
  { strength: "refuse", label: "Refuse" },
  { strength: "complete", label: "Needed to finish creation" },
  { strength: "review", label: "Allow, for our review" },
  { strength: "note", label: "Only note it" },
];

export const strengthLabel = (value: string) => STRENGTHS.find((s) => s.strength === value)?.label ?? value;

/** The draft as the server takes it, or why it cannot be yet. */
export function toBody(draft: Draft): { body: OwnCheckIn } | { problem: string } {
  if (draft.how !== "all" && !draft.value.trim()) {
    return { problem: draft.how === "trait" ? "Choose the trait it is about." : draft.how === "kind" ? "Choose the type." : "Write the start of the names." };
  }
  let condition: Condition;
  try {
    condition = toCondition(draft.blocks);
  } catch (e) {
    if (e instanceof BuildProblem) return { problem: e.message };
    throw e;
  }
  const value = draft.value.trim();
  return {
    body: {
      splat: draft.splat,
      category: draft.category,
      name: draft.how === "trait" ? value : null,
      name_prefix: draft.how === "prefix" ? value : null,
      kind: draft.how === "kind" ? value : null,
      mode: draft.mode,
      condition,
      strength: draft.strength,
      message: draft.message,
      step: draft.strength === "complete" && draft.step ? draft.step : null,
    },
  };
}

/** A saved check as a draft, to change it; null if the form has no blocks for its condition. */
export function draftOf(check: OwnCheckOut): Draft | null {
  let blocks: CondBlock[];
  try {
    blocks = fromCondition(check.condition);
  } catch (e) {
    if (e instanceof BuildProblem) return null;
    throw e;
  }
  const how: SubjectHow = check.name ? "trait" : check.name_prefix ? "prefix" : check.kind ? "kind" : "all";
  return {
    splat: check.splat,
    category: check.category,
    how,
    value: check.name ?? check.name_prefix ?? check.kind ?? "",
    mode: check.mode,
    blocks,
    strength: check.strength,
    message: check.message,
    step: check.step ?? "",
  };
}

// --- the catalogue -----------------------------------------------------------------

/** The kinds of trait a check can be about, or ask whether a sheet holds. */
export function subjectCategories(catalogue: CatalogueOut): CatalogueOut["categories"] {
  return catalogue.categories.filter((c) => !c.derived && catalogue.traits.some((t) => t.category === c.key));
}

export function namesIn(catalogue: CatalogueOut, category: string): string[] {
  return catalogue.traits.filter((t) => t.category === category).map((t) => t.name);
}

/** The catalogue types of a category's traits: "Clan", "General"… */
export function typesIn(catalogue: CatalogueOut, category: string): string[] {
  return [...new Set(catalogue.traits.filter((t) => t.category === category && t.kind).map((t) => t.kind!))].sort();
}

/** Every clan and bloodline, by full name. */
export function clans(catalogue: CatalogueOut): string[] {
  return namesIn(catalogue, "clan");
}

/** The highest rating a trait can be held at, for "holds a trait at a rating". */
export function topRating(catalogue: CatalogueOut, category: string, name: string): number | null {
  const c = catalogue.categories.find((x) => x.key === category);
  const t = catalogue.traits.find((x) => x.category === category && x.name === name);
  if (!c?.rated || t?.fixed_rating != null) return null;
  return Math.min(c.max_rating ?? 10, 10);
}
