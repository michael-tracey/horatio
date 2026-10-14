import { describe, expect, it } from "vitest";
import type { TraitOut } from "../../api/types";
import { applyFilter, filterChoices } from "./traitFilter";

const merit = (name: string, kind: string | null, requirement: string | null) =>
  ({ category: "merits", name, kind, requirement }) as unknown as TraitOut;

const MERITS = [
  merit("Acute Sense", "General", null),
  merit("Aura of Command", "Clan", "Ventrue"),
  merit("Paragon", "Clan", "Ventrue"),
  merit("Bloodline: Crusader", "Clan", "Ventrue: Crusader"),
  merit("Absent Sway", "Clan", "Toreador"),
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
      "kind:Clan",
      "kind:General",
      "req:Toreador",
      "req:Ventrue",
      "req:Ventrue: Crusader",
    ]);
  });
});
