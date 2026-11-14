import { describe, expect, it } from "vitest";
import type { PlayerCharacter } from "../../api/types";
import { characterLink, characterNotes, characterTroupe } from "./personCharacters";

const character = (c: Partial<PlayerCharacter> = {}) =>
  ({
    id: "c1",
    name: "Agnes",
    status: "active",
    retired: false,
    left_reason: null,
    creation_complete: true,
    asking_troupe: null,
    kind: "pc",
    splat: "vampire",
    home_troupe: null,
    npc_kind_name: null,
    npc_form: null,
    owner_troupe_id: null,
    owner_troupe: null,
    picture: null,
    clan: null,
    ...c,
  }) as PlayerCharacter;

const labels = (c: PlayerCharacter) => characterNotes(c).map((n) => n.label);

describe("characterNotes", () => {
  it("says an active character is active, and whether it is in creation or waiting for a troupe", () => {
    expect(labels(character())).toEqual(["Active"]);
    expect(labels(character({ creation_complete: false }))).toEqual(["Active", "In creation"]);
    expect(labels(character({ asking_troupe: "Ashes" }))).toEqual(["Active", "Waiting for Ashes"]);
  });

  it("says why a retired character left, when it was given", () => {
    expect(labels(character({ status: "retired", left_reason: "final_death" }))).toEqual(["Retired: Final Death"]);
    expect(labels(character({ status: "retired", left_reason: "off_field" }))).toEqual(["Retired: Off-field"]);
    expect(labels(character({ status: "retired" }))).toEqual(["Retired"]);
  });

  it("names what isn't a plain vampire PC", () => {
    expect(labels(character({ splat: "ghoul" }))).toEqual(["Active", "Ghoul"]);
    expect(labels(character({ kind: "npc", npc_kind_name: "Mortal" }))).toEqual(["Active", "NPC: Mortal"]);
  });
});

describe("characterTroupe and characterLink", () => {
  it("gives a PC's home troupe, or none, and an NPC's own troupe", () => {
    expect(characterTroupe(character({ home_troupe: "Ashes" }))).toBe("Ashes");
    expect(characterTroupe(character())).toBe("no home troupe");
    expect(characterTroupe(character({ kind: "npc", owner_troupe: "Ashes" }))).toBe("NPC of Ashes");
  });

  it("opens a Stock NPC in its builder, and anything else on its sheet", () => {
    expect(characterLink(character())).toBe("/characters/c1");
    expect(characterLink(character({ kind: "npc", npc_form: "stock", owner_troupe_id: "t1" }))).toBe("/troupes/t1/npcs/c1");
    expect(characterLink(character({ kind: "npc", npc_form: "sheeted", owner_troupe_id: "t1" }))).toBe("/characters/c1");
  });
});
