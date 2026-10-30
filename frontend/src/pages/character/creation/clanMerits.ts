/**
 * The merits a clan needs (MET: VTM pp. 237–238, #313): its bloodline merit, and the
 * rarity merit its setting asks for. The server gives them with the clan, from the merit
 * points (`clan_merits` on the creation state); the wizard shows them as the clan's,
 * and never offers them as picks.
 */

import type { CreationOut } from "../../../api/types";
import { pageText } from "../../troupe/bookPage";

export const RARITY_MERITS = ["Uncommon Clan", "Rare Clan", "Restricted Clan"];

/** Whether a merit comes with the clan rather than being picked: every bloodline merit,
 * and the rarity merits once the setting says how rare the clan is. */
export function comesWithClan(name: string, creation: Pick<CreationOut, "rarity_known">): boolean {
  return name.startsWith("Bloodline:") || (!!creation.rarity_known && RARITY_MERITS.includes(name));
}

/** The merit points the clan's merits take. */
export function clanPoints(creation: Pick<CreationOut, "clan_merits">): number {
  return (creation.clan_merits ?? []).reduce((sum, m) => sum + m.points, 0);
}

/** What the clan takes from the merit points, in a line: "The clan takes Bloodline: Coyote (2 points) from your merit points." */
export function clanMeritsLine(creation: Pick<CreationOut, "clan_merits">): string | null {
  const merits = creation.clan_merits ?? [];
  if (!merits.length) return null;
  const named = merits.map((m) => `${m.name} (${m.points} ${m.points === 1 ? "point" : "points"})`);
  const list = named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named.at(-1)}` : named[0];
  return `The clan takes ${list} from your merit points.`;
}

/** Why the clan needs a merit, with its page: "Gangrel: Coyote is a bloodline. (p. 238)" */
export function clanMeritWhy(merit: { why: string; page?: string | null }): string {
  return merit.page ? `${merit.why} (${pageText(merit.page)})` : merit.why;
}
