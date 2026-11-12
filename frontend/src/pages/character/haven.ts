import type { HavenAdvantageChoiceOut } from "../../api/types";

/**
 * A Haven's advantages against its owner's dots of Haven (MET: VTM p. 102): one
 * for each dot, and those a skill gives free (Security) on top. The server judges
 * the same; this is for the form, before it asks.
 */
export function havenCount(chosen: string[], advantages: HavenAdvantageChoiceOut[]): { used: number; free: string[] } {
  const free = new Set(advantages.filter((a) => a.free).map((a) => a.name));
  return { used: chosen.filter((a) => !free.has(a)).length, free: chosen.filter((a) => free.has(a)) };
}

/** Whether the owner can tick the advantage now: it is ticked already, or they have its skill and a dot for it. */
export function canChoose(name: string, chosen: string[], advantages: HavenAdvantageChoiceOut[], dots: number): boolean {
  if (chosen.includes(name)) return true;
  const advantage = advantages.find((a) => a.name === name);
  if (!advantage || !advantage.allowed) return false;
  return advantage.free || havenCount(chosen, advantages).used < dots;
}

/** "1 of 2 dots used, plus Security free". */
export function countText(chosen: string[], advantages: HavenAdvantageChoiceOut[], dots: number): string {
  const { used, free } = havenCount(chosen, advantages);
  return `${used} of ${dots} ${dots === 1 ? "dot" : "dots"} used${free.length ? `, plus ${free.join(" and ")} free` : ""}`;
}
