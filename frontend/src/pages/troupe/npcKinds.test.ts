import { describe, expect, it } from "vitest";
import { filterNpcs, groupedKinds, kindPages, kindsIn, resourceText, type NpcKind } from "./npcKinds";

const kind = (key: string, group: string): NpcKind => ({ key, group, name: key }) as NpcKind;

describe("NPC kinds", () => {
  it("groups the kinds in order, leaving out empty groups", () => {
    const groups = groupedKinds([kind("werewolf", "supernatural"), kind("mortal", "mortal"), kind("vampire", "vampire")]);
    expect(groups.map((g) => [g.label, g.kinds.map((k) => k.key)])).toEqual([
      ["Vampires and ghouls", ["vampire"]],
      ["Mortals", ["mortal"]],
      ["Other supernaturals", ["werewolf"]],
    ]);
  });

  it("says what a kind spends and where its rules are", () => {
    expect(resourceText({ name: "Rage", size: 10, per_turn: 3, regains: "1 every five turns" })).toBe("Rage 10, up to 3 a turn, regains 1 every five turns");
    expect(resourceText({ name: "Blood", size: 10, per_turn: 1, regains: "" })).toBe("Blood 10, 1 a turn");
    expect(resourceText({ name: "Blood", size: 5, per_turn: 0, regains: "" })).toBe("Blood 5, cannot be spent");
    expect(kindPages({ page: 494, to_page: 495 })).toBe("pp. 494–495");
    expect(kindPages({ page: 505, to_page: null })).toBe("p. 505");
  });

  it("filters NPCs by kind and form", () => {
    const npcs = [
      { name: "A", npc_kind: "werewolf", npc_kind_name: "Werewolf", npc_form: "stock" },
      { name: "B", npc_kind: "mage", npc_kind_name: "Mage", npc_form: "sheeted" },
      { name: "C", npc_kind: "werewolf", npc_kind_name: "Werewolf", npc_form: "sheeted" },
      { name: "D", npc_kind: "custom", npc_kind_name: "Angel", npc_form: "stock" },
    ];
    expect(filterNpcs(npcs, { kind: "", form: "" }).map((n) => n.name)).toEqual(["A", "B", "C", "D"]);
    expect(filterNpcs(npcs, { kind: "werewolf", form: "" }).map((n) => n.name)).toEqual(["A", "C"]);
    expect(filterNpcs(npcs, { kind: "werewolf", form: "stock" }).map((n) => n.name)).toEqual(["A"]);
    expect(filterNpcs(npcs, { kind: "", form: "sheeted" }).map((n) => n.name)).toEqual(["B", "C"]);
    expect(kindsIn(npcs)).toEqual([
      ["custom", "Custom"],
      ["mage", "Mage"],
      ["werewolf", "Werewolf"],
    ]);
  });
});
