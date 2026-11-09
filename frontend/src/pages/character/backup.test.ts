import { describe, expect, it } from "vitest";
import { backupFileName, countsText, sectionsQuery, slug } from "./backup";

describe("a character's backup file", () => {
  it("is named after the character, as the server names it", () => {
    expect(backupFileName("Agnes de Vries")).toBe("agnes-de-vries.horatio-character.json");
    expect(slug("  Ça va?  ")).toBe("a-va");
    expect(slug("!!!")).toBe("character");
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
