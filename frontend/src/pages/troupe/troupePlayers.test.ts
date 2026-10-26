import { describe, expect, it } from "vitest";
import type { RosterEntry } from "../../api/types";
import { searchPlayers, troupePlayers } from "./troupePlayers";

const entry = (over: Partial<RosterEntry>): RosterEntry => ({
  character_id: crypto.randomUUID(),
  character_name: "Anon",
  player_name: "Pat",
  player_id: "p1",
  player_handle: "pat",
  kind: "pc",
  retired: false,
  titles: [],
  picture: null,
  clan: null,
  social_age: "Neonate",
  home: true,
  waiting: false,
  disciplines_waiting: 0,
  joined_at: "2026-01-01T00:00:00Z",
  ...over,
});

describe("troupePlayers", () => {
  it("shows a player once, with a home and a visiting character", () => {
    const players = troupePlayers([
      entry({ character_name: "Visitor", home: false }),
      entry({ character_name: "Homebody", home: true }),
    ]);
    expect(players).toHaveLength(1);
    expect(players[0]!.characters.map((c) => c.character_name)).toEqual(["Homebody", "Visitor"]);
  });

  it("leaves out NPCs and retired characters, and the players who only have those", () => {
    const players = troupePlayers([
      entry({ kind: "npc", player_id: null, player_name: "NPC", player_handle: null }),
      entry({ player_id: "p2", player_name: "Quinn", retired: true }),
      entry({ player_id: "p3", player_name: "Robin" }),
    ]);
    expect(players.map((p) => p.name)).toEqual(["Robin"]);
  });

  it("sorts by name", () => {
    const players = troupePlayers([entry({ player_id: "b", player_name: "Zed" }), entry({ player_id: "a", player_name: "Abe" })]);
    expect(players.map((p) => p.name)).toEqual(["Abe", "Zed"]);
  });
});

describe("searchPlayers", () => {
  const players = troupePlayers([
    entry({ player_id: "a", player_name: "Abe", character_name: "Lucien" }),
    entry({ player_id: "b", player_name: "Zed", character_name: "Odile" }),
  ]);

  it("matches a player or a character", () => {
    expect(searchPlayers(players, "zed").map((p) => p.name)).toEqual(["Zed"]);
    expect(searchPlayers(players, "LUC").map((p) => p.name)).toEqual(["Abe"]);
    expect(searchPlayers(players, " ")).toHaveLength(2);
  });
});
