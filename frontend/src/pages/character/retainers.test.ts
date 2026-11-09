import { describe, expect, it } from "vitest";
import { addsRetainers, backText, givingMerits, growthText, neglectText, placeRetainers, retainerName, retainerSource, sectionLabel } from "./retainers";

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

describe("each Retainer under its own row of the sheet (#586)", () => {
  const row = (category: string, name: string, detail = "") => ({ category, name, detail });
  const bocephus = row("backgrounds", "Retainers", "Bocephus");
  const mags = row("backgrounds", "Retainers", "Mags");
  const companion = row("merits", "Ardent Companion");
  const hounds = row("merits", "Master of the Hounds");
  const retainer = (name: string, bought: boolean, from_merit = "") => ({ name, bought, from_merit });

  it("lists one bought under its own Retainers row, by name, and one from a merit under the merit", () => {
    const listed = [retainer("Bocephus", true), retainer("Mags", true), retainer("", false, "Ardent Companion"), retainer("Second hound", false, "Master of the Hounds")];
    const under = placeRetainers([bocephus, row("backgrounds", "Haven"), mags, companion, hounds], listed);
    expect(under.get(bocephus)).toEqual([listed[0]]);
    expect(under.get(mags)).toEqual([listed[1]]);
    expect(under.get(companion)).toEqual([listed[2]]);
    expect(under.get(hounds)).toEqual([listed[3]]);
    expect(under.size).toBe(4);
  });
  it("lists one held without a name under its own row, with those listed before each was bought on its own", () => {
    const unnamed = row("backgrounds", "Retainers");
    const listed = [retainer("Bocephus", true), retainer("", true), retainer("Rook", false), retainer("Old hound", false, "Master of the Hounds")];
    const under = placeRetainers([bocephus, unnamed], listed);
    expect(under.get(bocephus)).toEqual([listed[0]]);
    // The merit is no longer held, so its Retainer goes there too.
    expect(under.get(unnamed)).toEqual([listed[1], listed[2], listed[3]]);
  });
  it("lists the rest under the first merit with a Retainer when none is bought, and nowhere when nothing holds one", () => {
    const listed = [retainer("Rex", false, "Ardent Companion"), retainer("Rook", false)];
    expect(placeRetainers([hounds, companion], listed).get(companion)).toEqual(listed);
    expect(placeRetainers([hounds], [retainer("Rook", false)]).size).toBe(0);
  });
  it("names each row's Retainers", () => {
    expect(sectionLabel(bocephus)).toBe("Retainer: Bocephus");
    expect(sectionLabel(row("backgrounds", "Retainers"))).toBe("Retainer not yet named");
    expect(sectionLabel(companion)).toBe("Retainers from Ardent Companion");
  });
  it("knows a merit that speaks of Retainers, where one can be added by hand", () => {
    expect(addsRetainers("A Retainer can be a hellhound, and you get two of them for one background.")).toBe(true);
    expect(addsRetainers("Spend it as if it were Contacts, Retainers or Allies.")).toBe(true);
    expect(addsRetainers("Your blood is thin.")).toBe(false);
    expect(addsRetainers(undefined)).toBe(false);
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
