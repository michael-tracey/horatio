import type { ExpendableOut, OtherOut, SeenOut } from "../../api/types";
import type { ShownEntry } from "./tracker";

/** Leadership's uses a game, as the Play View counts them: one a dot (MET: VTM p. 310). */
export const LEADERSHIP = "trait:skills/Leadership/";

/** The character's Leadership under Uses this game, if it has any. */
export function leadershipOf(expendables: ExpendableOut[]): ExpendableOut | undefined {
  return expendables.find((e) => e.key.startsWith(LEADERSHIP));
}

/**
 * Another's status as it shows now: what was learned by a tap since undone here
 * (perhaps not yet sent) is forgotten at once, as the server will forget it.
 */
export function shownSeen(seen: SeenOut, log: ShownEntry[]): SeenOut {
  if (!seen.learned_by || !log.some((e) => e.id === seen.learned_by && e.undone)) return seen;
  return { ...seen, known: false, learned_by: null, patron: null, place: null, story: null };
}

/** The others whose name has `query` in it, ignoring case. */
export function matching(others: OtherOut[], query: string): OtherOut[] {
  const q = query.trim().toLowerCase();
  return q ? others.filter((o) => o.name.toLowerCase().includes(q)) : others;
}
