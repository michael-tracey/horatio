import type { RosterEntry } from "../../api/types";

export type TroupePlayer = {
  id: string;
  name: string;
  handle: string | null;
  characters: RosterEntry[];
};

/**
 * The troupe's players: everyone with an active PC here, home or visiting, once
 * each, sorted by name, their characters home first. NPCs and retired
 * characters count for nothing.
 */
export function troupePlayers(roster: RosterEntry[]): TroupePlayer[] {
  const byId = new Map<string, TroupePlayer>();
  for (const e of roster) {
    if (e.kind !== "pc" || e.retired || !e.player_id) continue;
    const player = byId.get(e.player_id) ?? { id: e.player_id, name: e.player_name, handle: e.player_handle, characters: [] };
    player.characters.push(e);
    byId.set(e.player_id, player);
  }
  return [...byId.values()]
    .map((p) => ({ ...p, characters: p.characters.sort((a, b) => Number(b.home) - Number(a.home) || a.character_name.localeCompare(b.character_name)) }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** The players whose name, handle or any character's name has the search in it. */
export function searchPlayers(players: TroupePlayer[], search: string): TroupePlayer[] {
  const q = search.trim().toLowerCase();
  if (!q) return players;
  return players.filter((p) => `${p.name} ${p.handle ?? ""} ${p.characters.map((c) => c.character_name).join(" ")}`.toLowerCase().includes(q));
}
