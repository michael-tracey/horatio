import type { TargetChoiceOut } from "../../api/types";

/** An action's extra fields, as the form keeps them. */
type Fields = Record<string, unknown> | undefined;

export type Counter = "cancel" | "watch";
export const COUNTER_NAMES: Record<Counter, string> = { cancel: "Cancel", watch: "Watch" };

/** The characters an action is aimed at, by id (#507). */
export function aimedAt(fields: Fields): string[] {
  const raw = fields?.aimed_at;
  return Array.isArray(raw) ? raw.filter((id): id is string => typeof id === "string") : [];
}

export function counterOf(fields: Fields): Counter | null {
  const raw = fields?.counter;
  return raw === "cancel" || raw === "watch" ? raw : null;
}

export function projectOf(fields: Fields): string {
  return typeof fields?.project_id === "string" ? fields.project_id : "";
}

/** The fields with `key` set, or left out when `value` is empty. */
function withField(fields: Fields, key: string, value: unknown): Record<string, unknown> {
  const { [key]: _old, ...rest } = fields ?? {};
  const empty = value == null || value === "" || (Array.isArray(value) && value.length === 0);
  return empty ? rest : { ...rest, [key]: value };
}

/**
 * The fields aimed at `ids`. A Cancel or Watch is aimed at one character, so it goes
 * when there is any other number of them.
 */
export function withTargets(fields: Fields, ids: string[]): Record<string, unknown> {
  const aimed = withField(fields, "aimed_at", ids);
  return ids.length === 1 ? aimed : withField(aimed, "counter", null);
}

export function withCounter(fields: Fields, counter: Counter | null): Record<string, unknown> {
  return withField(fields, "counter", counter);
}

export function withProject(fields: Fields, projectId: string): Record<string, unknown> {
  return withField(fields, "project_id", projectId);
}

/**
 * The actions an answer costs: two when it is aimed at someone whose Haven doubles
 * it (MET: VTM p. 102), unless staff say it isn't against them.
 */
export function actionCost(fields: Fields, targets: TargetChoiceOut[], notAgainst = false): number {
  if (notAgainst) return 1;
  const ids = new Set(aimedAt(fields));
  return targets.some((t) => ids.has(t.id) && t.cost > 1) ? 2 : 1;
}
