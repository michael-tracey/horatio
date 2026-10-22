/**
 * Influence actions (backend: horatio.influence). A general action has a level and
 * needs a rating at least that, or one less when it uses one of the character's
 * own specialisations of the type (MET: VtM core, p. 512). A conflict action
 * (Attack, Block, Boost, Defend, a discovery block) has no level.
 */
import type { InfluenceActionOut, InfluenceStandingOut } from "./api/types";

export type InfluenceType = InfluenceStandingOut["type"];

export const TYPE_NAMES: Record<InfluenceType, string> = { elite: "Elite", underworld: "Underworld" };

type Fields = Record<string, unknown> | undefined;

/** The action an answer's fields name: by key, or by level for an answer from before actions had names. */
export function chosenAction(actions: InfluenceActionOut[], fields: Fields): InfluenceActionOut | undefined {
  const key = fields?.action;
  if (typeof key === "string" && key) return actions.find((a) => a.key === key);
  const level = fields?.level;
  if (typeof level === "number") return actions.find((a) => !a.conflict && a.level === level);
  return undefined;
}

/** Whether the specialisation is one of the character's own, which counts the rating one higher. */
export function holds(standing: InfluenceStandingOut, specialization: unknown): boolean {
  return typeof specialization === "string" && standing.held.includes(specialization);
}

export function reachable(standing: InfluenceStandingOut, action: InfluenceActionOut, specialization: unknown): boolean {
  return action.level == null || action.level <= standing.rating + (holds(standing, specialization) ? 1 : 0);
}

/** The actions the form offers with this specialisation. */
export function offered(standing: InfluenceStandingOut, specialization: unknown): InfluenceActionOut[] {
  return standing.actions.filter((a) => reachable(standing, a, specialization));
}

/** What to say under the action: when a specialisation makes the difference. */
export function reachNote(standing: InfluenceStandingOut, specialization: unknown, action: InfluenceActionOut | undefined): string | null {
  const type = TYPE_NAMES[standing.type];
  if (action?.level != null && action.level > standing.rating && holds(standing, specialization))
    return `Your ${String(specialization)} specialisation counts your ${type} as ${standing.rating + 1} for this.`;
  if (standing.held.length && !holds(standing, specialization) && standing.rating < 10)
    return `Choose one of your own specialisations to reach a level-${standing.rating + 1} action.`;
  return null;
}
