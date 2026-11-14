import type { MotifTouchedOut } from "../../api/types";

/** How often a theme or mood is touched: "2 scenes, 1 quest", or "Not touched yet". */
export function touchedText(m: Pick<MotifTouchedOut, "scenes" | "quests">): string {
  const parts = [
    [m.scenes.length, "scene"],
    [m.quests.length, "quest"],
  ] as const;
  const said = parts.filter(([n]) => n > 0).map(([n, noun]) => `${n} ${noun}${n === 1 ? "" : "s"}`);
  return said.length ? said.join(", ") : "Not touched yet";
}

/** The ids of the tags, with one put on or taken off. */
export function toggled(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id];
}
