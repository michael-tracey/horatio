import { describe, expect, it } from "vitest";
import { kindGroups, kindLabel, kindSlug } from "./specializations";

describe("the Specialisations tab's own tabs", () => {
  it("names each kind in the address and on its tab", () => {
    expect(kindSlug("lore_specializations")).toBe("lore");
    expect(kindSlug("influence_elite_specializations")).toBe("influence-elite");
    expect(kindLabel("Lore Specializations")).toBe("Lore");
    expect(kindLabel("Influence: Elite")).toBe("Influence: Elite");
  });

  it("groups the kinds as on a sheet, in order", () => {
    const kinds = [
      { category: "lore_specializations", name: "Lore Specializations", group: "Skills" },
      { category: "haven_specializations", name: "Haven Specializations", group: "Backgrounds" },
      { category: "drive_specializations", name: "Drive Specializations", group: "Skills" },
    ];
    expect(kindGroups(kinds).map((g) => [g.label, g.kinds.map((k) => kindSlug(k.category))])).toEqual([
      ["Skills", ["lore", "drive"]],
      ["Backgrounds", ["haven"]],
    ]);
  });
});
