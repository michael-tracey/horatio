import { describe, expect, it } from "vitest";
import { backupFileName, countsText, fileStem, namePart, sectionsQuery } from "./backup";

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
