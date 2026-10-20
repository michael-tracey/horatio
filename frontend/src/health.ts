/** Health levels as the paper sheet shows them, for the sheet page and the printed sheet alike. */

/** The line under the example BNS sheet's Health Levels heading. */
export const HEALTH_RULE = "Incapacitated characters lose their simple action.";

/** The paper sheet's rows, in its order. */
const LEVELS = ["Healthy", "Injured", "Incapacitated"];

type TraitLike = { category: string; name: string; rating: number | null };

export type HealthRow<T extends TraitLike> = {
  name: string;
  boxes: number;
  /** The sheet's trait for the level, if it holds one. */
  trait: T | undefined;
};

/**
 * One row per health level, Healthy, Injured then Incapacitated, each with a box
 * per level the sheet gives it (after Rugged, Permanent Wound, Fortitude...). A
 * level with none left still has its row, with no boxes. Any other level a rule
 * set adds comes after them.
 */
export function healthRows<T extends TraitLike>(traits: T[]): HealthRow<T>[] {
  const held = traits.filter((t) => t.category === "health_levels");
  const names = [...LEVELS, ...held.map((t) => t.name).filter((n) => !LEVELS.includes(n))];
  return names.map((name) => {
    const trait = held.find((t) => t.name === name);
    return { name, boxes: Math.max(0, trait?.rating ?? 0), trait };
  });
}
