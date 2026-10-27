import type { EquipmentFactsOut, EquipmentItemOut, EquipmentOut, EquipmentQualityOut, EquipmentTemplateOut, TroupeTemplateOut } from "../../api/types";

export type Kind = "melee" | "ranged" | "protective" | "miscellaneous";
export type Grade = "cheap" | "standard" | "special";
export type DraftQuality = { name: string; detail: string };
export type DraftEffect = { name: string; effect: string };

/** An item as the editor builds it, before it is given or changed. */
export type Draft = {
  name: string;
  kind: Kind;
  grade: Grade;
  qualities: DraftQuality[];
  crafted: boolean;
  effects: DraftEffect[];
  description: string;
  staff_note: string;
};

export const NEW_ITEM: Draft = { name: "", kind: "melee", grade: "standard", qualities: [], crafted: false, effects: [], description: "", staff_note: "" };

export const GRADE_NAMES: Record<Grade, string> = {
  cheap: "Cheap (1 quality)",
  standard: "Standard or expensive (up to 2)",
  special: "Special (any number)",
};

/** A template, the book's or the troupe's, as a draft to adjust. Its name is the item's. */
export function fromTemplate(template: EquipmentTemplateOut | TroupeTemplateOut): Draft {
  const own = "effects" in template ? template : null;
  return {
    ...NEW_ITEM,
    name: template.name,
    kind: template.kind as Kind,
    grade: template.grade as Grade,
    qualities: template.qualities.map((q) => ({ name: q.name, detail: q.detail ?? "" })),
    crafted: own?.crafted ?? false,
    effects: own?.effects.map((e) => ({ ...e })) ?? [],
    description: own?.description ?? "",
  };
}

/** An item already held, as a draft to change. */
export function fromItem(item: EquipmentItemOut): Draft {
  return {
    name: item.name,
    kind: item.kind as Kind,
    grade: item.grade as Grade,
    qualities: item.qualities.map((q) => ({ name: q.name, detail: q.detail })),
    crafted: item.crafted,
    effects: item.effects.map((e) => ({ ...e })),
    description: item.description,
    staff_note: item.staff_note ?? "",
  };
}

/** What the API takes: a special item's effects only, and details only where given. */
export function body(draft: Draft) {
  return {
    name: draft.name,
    kind: draft.kind,
    grade: draft.grade,
    qualities: draft.qualities.map((q) => ({ name: q.name, detail: q.detail.trim() })),
    crafted: draft.crafted,
    effects: draft.grade === "special" ? draft.effects : [],
    description: draft.description,
    staff_note: draft.staff_note,
  };
}

/** The qualities an item of `kind` can take, leaving out those it has unless repeatable. */
export function qualityChoices(rules: EquipmentOut, kind: Kind, chosen: DraftQuality[]): EquipmentQualityOut[] {
  return rules.qualities.filter((q) => q.kind === kind && (q.repeatable || !chosen.some((c) => c.name === q.name)));
}

export function qualityOf(rules: EquipmentOut, kind: string, name: string): EquipmentQualityOut | undefined {
  return rules.qualities.find((q) => q.kind === kind && q.name === name);
}

/** A quality as it reads: "Customized: hacking". */
export function qualityText(q: { name: string; detail?: string | null }): string {
  return q.detail ? `${q.name}: ${q.detail}` : q.name;
}

/** The facts that apply, in a line: "2 hands · 2 damage · 12 shots · half a mile". */
export function factsText(facts: EquipmentFactsOut): string {
  const parts: string[] = [];
  if (facts.hands != null) parts.push(facts.hands === 1 ? "1 hand" : `${facts.hands} hands`);
  if (facts.damage != null) parts.push(`${facts.damage} damage`);
  if (facts.shots != null) parts.push(facts.shots === 1 ? "1 shot" : `${facts.shots} shots`);
  if (facts.range) parts.push(`range ${facts.range}`);
  return parts.join(" · ");
}

/** Kind, grade and crafting in a few words: "Special melee weapon", "Cheap protective gear". */
export function kindText(rules: EquipmentOut | undefined, item: { kind: string; grade: string; crafted: boolean }): string {
  const kind = rules?.kinds.find((k) => k.key === item.kind)?.name ?? item.kind;
  const grade = item.grade === "standard" ? "" : `${item.grade} `;
  const text = `${item.crafted ? "crafted " : ""}${grade}${kind.toLowerCase()}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
