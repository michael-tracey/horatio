/** The Log influence tool's words and choices (issue #134; backend: horatio.influence_log). */
import type { CharacterChoice, CycleChoice, CycleUseOut } from "../../api/types";
import { TYPE_NAMES, type InfluenceType } from "../../influence";

/** The troupe's characters whose names have what was typed in them, those starting with it first. */
export function findCharacters(characters: CharacterChoice[], typed: string): CharacterChoice[] {
  const q = typed.trim().toLocaleLowerCase();
  if (!q) return characters;
  const named = characters.filter((c) => c.name.toLocaleLowerCase().includes(q));
  const starts = (c: CharacterChoice) => (c.name.toLocaleLowerCase().startsWith(q) ? 0 : 1);
  return [...named].sort((a, b) => starts(a) - starts(b));
}

/** The specialisations to offer: the character's own of the type first, then every other. */
export function specializationGroups(held: string[], all: string[], chosen = ""): { own: string[]; others: string[] } {
  const own = [...new Set(held)];
  const others = [...new Set([...all, ...(chosen && !held.includes(chosen) ? [chosen] : [])])].filter((s) => !own.includes(s));
  return { own, others: others.sort((a, b) => a.localeCompare(b)) };
}

/** When a cycle dates an entry: when it opened, or when it closes if it has not opened yet. */
export function cycleDate(cycle: Pick<CycleChoice, "opened_at" | "closes_at">): string {
  return cycle.opened_at ?? cycle.closes_at;
}

/**
 * A warning, never a refusal, when a PC's entries for a cycle would go over its
 * allowance of the type. Staff may log over it on purpose; NPCs have none.
 */
export function allowanceWarning(use: CycleUseOut | undefined, adding: number, who: string, cycleName: string): string | null {
  if (!use || use.allowance == null || use.logged + adding <= use.allowance) return null;
  const type = TYPE_NAMES[use.type as InfluenceType];
  const has = `${who} has ${use.allowance} ${type} ${use.allowance === 1 ? "action" : "actions"} in ${cycleName}`;
  return `${has}, and this makes ${use.logged + adding} logged. You can still log it.`;
}

export type EntryFields = {
  type: InfluenceType;
  /** "c:<character id>", "name" for someone not in Horatio, or "" for no one yet. */
  who: string;
  name: string;
  specialization: string;
  action_key: string;
  purpose: string;
  times: number;
  blocks: number;
  /** A datetime-local value, on the reader's clock. */
  happened_at: string;
  cycle_id: string;
  needs_details: boolean;
};

/** What Add another starts the next entry with: the same date, cycle and character, and its type; the rest cleared. */
export function another(form: EntryFields): EntryFields {
  return {
    ...form,
    specialization: "",
    action_key: "",
    purpose: "",
    times: 1,
    blocks: 0,
    needs_details: false,
  };
}
