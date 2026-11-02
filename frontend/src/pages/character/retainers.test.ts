import { describe, expect, it } from "vitest";
import { backText, givingMerits, growthText, neglectText, retainerName, retainerSource } from "./retainers";

describe("a Retainer in a list", () => {
  it("is named, or says it has no name yet", () => {
    expect(retainerName({ name: "Bocephus" })).toBe("Bocephus");
    expect(retainerName({ name: "" })).toBe("A Retainer not yet named");
    expect(retainerName({ name: "", kind: "Ghouled animal" })).toBe("Ghouled animal, not yet named");
  });
  it("knows the merits whose rules give a Retainer, each once", () => {
    const given = { given: true, from_merit: "Ardent Companion" };
    expect(givingMerits([given, given, { given: false, from_merit: "Master of the Hounds" }])).toEqual(["Ardent Companion"]);
  });
  it("says where its dots come from when they are not bought on the sheet", () => {
    expect(retainerSource({ bought: true, from_merit: "" })).toBeNull();
    expect(retainerSource({ bought: false, from_merit: "Ghostly Retainer" })).toBe("from Ghostly Retainer");
    expect(retainerSource({ bought: false, from_merit: "" })).toBe("listed before each Retainer was bought on its own");
  });
});

describe("a lost Retainer", () => {
  const date = (iso: string) => iso;
  const lost = { lost: "killed", back_from: "2026-11-14", back_games: 3, back_on: null, away: true };
  it("says when its dots come back, or what they wait on while the games are not scheduled", () => {
    expect(backText(lost, date)).toBe("Its dots come back once 3 games have gone by since, and not before 2026-11-14.");
    expect(backText({ ...lost, back_on: "2026-11-22" }, date)).toBe("Its dots come back on 2026-11-22.");
    expect(backText({ ...lost, back_on: "2026-11-22", away: false }, date)).toBe("Its dots came back on 2026-11-22.");
  });
  it("says nothing for one serving", () => {
    expect(backText({ ...lost, lost: null }, date)).toBeNull();
  });
});

describe("a Retainer under the house rules for upkeep and growth (#442)", () => {
  const date = (iso: string) => `on ${iso}`;
  it("says when it went neglected", () => {
    expect(neglectText({ neglected_on: null }, date)).toBeNull();
    expect(neglectText({ neglected_on: "2026-11-01" }, date)).toBe("Neglected since on 2026-11-01: its upkeep went unpaid.");
  });
  it("says what its growth banked, and what its NPC has to spend", () => {
    expect(growthText({ banked_xp: 0, npc_xp: null, npc_name: null })).toBeNull();
    expect(growthText({ banked_xp: 8, npc_xp: null, npc_name: null })).toBe("8 XP banked");
    expect(growthText({ banked_xp: 4, npc_xp: 6, npc_name: "Marta" })).toBe("4 XP banked · Marta has 6 XP to spend");
    expect(growthText({ banked_xp: 0, npc_xp: 0, npc_name: null })).toBe("Its NPC has 0 XP to spend");
  });
});
