import { describe, expect, it } from "vitest";
import type { CatalogueOut, SheetTraitOut } from "../../api/types";
import { groupTraits, swapOptions } from "./SheetTab";

const trait = (category: string, category_name: string, group: string, name: string): SheetTraitOut => ({
  id: name,
  category,
  category_name,
  group,
  name,
  detail: "",
  rating: 1,
  free_rating: 0,
  min_rating: 0,
  pending_from: null,
  granted_rating: 0,
  granted_by: [],
  free_choices: [],
  note: "",
});

describe("groupTraits", () => {
  it("groups by sheet group, in the rule set's category order", () => {
    const catalogue = {
      categories: [
        { key: "clan", name: "Clan", group: "Identity", rated: false, max_rating: null },
        { key: "skills", name: "Skills", group: "Skills", rated: true, max_rating: 10 },
      ],
    } as CatalogueOut;

    const groups = groupTraits(
      [trait("skills", "Skills", "Skills", "Brawl"), trait("clan", "Clan", "Identity", "Brujah")],
      catalogue,
    );

    expect([...groups.keys()]).toEqual(["Identity", "Skills"]);
    expect(groups.get("Skills")?.get("Skills")?.map((t) => t.name)).toEqual(["Brawl"]);
  });
});

describe("swapOptions", () => {
  const catalogue = {
    categories: [
      { key: "focus_physicals", name: "Physical Focus", group: "Attributes", rated: true, max_rating: null, change_cost: 10 },
      { key: "skills", name: "Skills", group: "Skills", rated: true, max_rating: 10, change_cost: null },
    ],
    traits: [
      { category: "focus_physicals", name: "Strength" },
      { category: "focus_physicals", name: "Dexterity" },
      { category: "focus_physicals", name: "Stamina" },
      { category: "skills", name: "Brawl" },
    ],
  } as unknown as CatalogueOut;

  it("offers the other focuses, at the category's cost", () => {
    const strength = trait("focus_physicals", "Physical Focus", "Attributes", "Strength");
    expect(swapOptions(strength, [strength], catalogue)).toEqual({ cost: 10, others: ["Dexterity", "Stamina"] });
  });

  it("offers nothing for a focus a merit gives", () => {
    const strength = { ...trait("focus_physicals", "Physical Focus", "Attributes", "Strength"), granted_rating: 1, granted_by: ["Dust in the Wind"] };
    expect(swapOptions(strength, [strength], catalogue)).toBeNull();
  });

  it("offers nothing for categories that cannot be swapped", () => {
    const brawl = trait("skills", "Skills", "Skills", "Brawl");
    expect(swapOptions(brawl, [brawl], catalogue)).toBeNull();
  });
});
