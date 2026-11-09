import { describe, expect, it } from "vitest";
import { backupFileName, countsText, fileStem, importSummary, isZip, namePart, outcomeText, sectionsQuery } from "./backup";

describe("a character's backup file", () => {
  it("is named for the character and the day it was exported, as the server names it", () => {
    expect(backupFileName("Agnes de Vries", new Date(2026, 10, 9))).toBe("AgnesdeVries-2026-11-09.horatio-character.json");
    expect(fileStem("Agnes de Vries", new Date(2026, 0, 5))).toBe("AgnesdeVries-2026-01-05");
  });
  it("folds accents, and drops spaces, other letters and what a file name can't hold", () => {
    expect(namePart("Zoë Brontë-Ågren")).toBe("ZoeBronte-Agren");
    expect(namePart("Ślęża Łódź")).toBe("Slezaodz");
    expect(namePart("O'Brien, \"Red\" / Jr.?")).toBe("OBrienRedJr");
    expect(namePart("con:sole*<>|")).toBe("console");
  });
  it("is \"character\" when nothing of the name is left", () => {
    expect(namePart("Ναταλία")).toBe("character");
    expect(namePart("伊藤 光")).toBe("character");
    expect(namePart("   ")).toBe("character");
  });
  it("asks for the sections chosen, in their order", () => {
    expect(sectionsQuery(new Set())).toBe("");
    expect(sectionsQuery(new Set(["titles", "equipment"]))).toBe("?sections=equipment&sections=titles");
    expect(sectionsQuery(new Set(["retainers"]), { which: "npcs" })).toBe("?sections=retainers&which=npcs");
  });
  it("counts what a review found", () => {
    expect(countsText({ new: 12, differs: 0, cannot: 0 })).toBe("12 new");
    expect(countsText({ new: 12, differs: 1, cannot: 2 })).toBe("12 new, 1 held otherwise here, 2 left out");
  });
});

describe("a troupe's import", () => {
  const entry = { outcome: "held" as const, problem: null, player: null, duplicate: null };
  it("says what happens to each character, and who gives a held one", () => {
    expect(outcomeText(entry, true)).toBe("Held as an NPC, to give to its player later.");
    expect(outcomeText(entry, false)).toBe("Held as an NPC: a storyteller gives it to its player.");
    expect(outcomeText({ ...entry, outcome: "given", player: { id: "1", handle: "agnes", display_name: "Agnes", plays_here: false } }, true)).toBe(
      "Given to @agnes, at home here and accepted.",
    );
    expect(outcomeText({ ...entry, outcome: "undecided", duplicate: { character_id: "2", name: "Lucien", whose: "an NPC of the troupe" } }, true)).toBe(
      "Lucien, an NPC of the troupe, has this name: skip it, replace it or add a copy.",
    );
    expect(outcomeText({ ...entry, outcome: "cannot", problem: "That file is from a newer Horatio." }, true)).toBe("That file is from a newer Horatio.");
  });
  it("counts what happens", () => {
    expect(importSummary([{ outcome: "new" }, { outcome: "new" }, { outcome: "given" }, { outcome: "cannot" }])).toBe(
      "2 new NPCs, 1 given to its player, 1 can't be imported",
    );
    expect(importSummary([])).toBe("Nothing");
  });
  it("knows a zip by its name or its type", () => {
    expect(isZip({ name: "Court-characters-2026-11-09.ZIP", type: "" })).toBe(true);
    expect(isZip({ name: "download", type: "application/zip" })).toBe(true);
    expect(isZip({ name: "Agnes.horatio-character.json", type: "application/json" })).toBe(false);
  });
});
