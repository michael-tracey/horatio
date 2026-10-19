import { describe, expect, it } from "vitest";
import type { TraitOut } from "../../api/types";
import { applyFilter, filterChoices, quickPicks } from "./traitFilter";

const merit = (name: string, kind: string | null, requirement: string | null) =>
  ({ category: "merits", name, kind, requirement }) as unknown as TraitOut;

const MERITS = [
  merit("Acute Sense", "General", null),
  merit("Aura of Command", "Clan", "Ventrue"),
  merit("Paragon", "Clan", "Ventrue"),
  merit("Bloodline: Crusader", "Clan", "Ventrue: Crusader"),
  merit("Absent Sway", "Clan", "Toreador"),
  merit("Harpy's Favour", "Camarilla", null),
];
const names = (traits: TraitOut[]) => traits.map((t) => t.name);

describe("merit filters", () => {
  it("shows one clan's merits, bloodlines included", () => {
    expect(names(applyFilter(MERITS, "req:Ventrue"))).toEqual(["Aura of Command", "Paragon", "Bloodline: Crusader"]);
  });

  it("shows one kind", () => {
    expect(names(applyFilter(MERITS, "kind:General"))).toEqual(["Acute Sense"]);
  });

  it("shows what the character can take", () => {
    expect(names(applyFilter(MERITS, "can", { "Absent Sway": "Toreador only" }))).not.toContain("Absent Sway");
  });

  it("offers the kinds and clans the list has", () => {
    expect(filterChoices(MERITS, true).map((c) => c.value)).toEqual([
      "can",
      "all",
      "kind:Camarilla",
      "kind:Clan",
      "kind:General",
      "req:Toreador",
      "req:Ventrue",
      "req:Ventrue: Crusader",
    ]);
  });
});

describe("quick picks", () => {
  it("offer the character's clan, bloodlines included, and sect", () => {
    const sheet = [
      { category: "clan", name: "Ventrue: Crusader" },
      { category: "sect", name: "Camarilla" },
    ];
    expect(quickPicks(MERITS, sheet)).toEqual([
      { value: "req:Ventrue", label: "Ventrue" },
      { value: "kind:Camarilla", label: "Camarilla" },
    ]);
  });

  it("leave out a clan or sect with nothing in the list", () => {
    expect(quickPicks(MERITS, [{ category: "clan", name: "Gangrel" }, { category: "sect", name: "Sabbat" }])).toEqual([]);
  });
});

describe("what this character can take", () => {
  it("hides only what no choice could allow", () => {
    const barred = { "Absent Sway": "Absent Sway is only for Toreador." };
    expect(names(applyFilter(MERITS, "can", barred))).not.toContain("Absent Sway");
    expect(names(applyFilter(MERITS, "can", barred))).toContain("Paragon");
  });
});
