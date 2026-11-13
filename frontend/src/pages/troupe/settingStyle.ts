import type { SettingEntryOut } from "../../api/types";

export type Kind = SettingEntryOut["kind"];

/** The ids with `id` taken out and put back at `to`, the others keeping their order. */
export function moved(ids: string[], id: string, to: number): string[] {
  const rest = ids.filter((x) => x !== id);
  const at = Math.max(0, Math.min(to, rest.length));
  return [...rest.slice(0, at), id, ...rest.slice(at)];
}
