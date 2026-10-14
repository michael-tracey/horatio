import { describe, expect, it } from "vitest";
import type { CatalogueOut, SheetTraitOut } from "../../api/types";
import { groupTraits } from "./SheetTab";

const trait = (category: string, category_name: string, group: string, name: string): SheetTraitOut => ({
  id: name,
  category,
  category_name,
  group,
  name,
  detail: "",
  rating: 1,
  free_rating: 0,
  approved_rating: null,
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
