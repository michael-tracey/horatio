import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "../../api/types";
import { categoryInfo, choiceInfo, partInfo } from "./categoryInfo";

const category = (key: string, group: string, extra: Partial<CatalogueOut["categories"][number]> = {}) => ({
  key,
  name: key,
  group,
  rated: true,
  max_rating: null,
  ...extra,
});

const catalogue = {
  splat: "vampire",
  name: "Vampire",
  traits: [],
  categories: [
    category("focus_physicals", "Attributes", { change_cost: 10 }),
    category("merits", "Merits and Flaws", { points_limit: 7 }),
    category("flaws", "Merits and Flaws", { points_limit: 5 }),
  ],
} as CatalogueOut;

describe("partInfo", () => {
  it("says what a part is, with the price the catalogue gives", () => {
    expect(partInfo("Skills", catalogue)?.facts).toEqual([]);
    expect(partInfo("Attributes", catalogue)?.facts).toEqual(["After creation, swapping a focus for another costs 10 XP."]);
  });

  it("works before the catalogue has loaded, and gives nothing for a part it has no words for", () => {
    expect(partInfo("Skills", undefined)?.about).toBeTruthy();
    expect(partInfo("Health Levels", catalogue)).toBeNull();
  });
});

describe("categoryInfo", () => {
  it("gives the limit from the catalogue, not a number of its own", () => {
    expect(categoryInfo("merits", catalogue)?.facts).toEqual(["A character holds at most 7 points of merits."]);
    expect(categoryInfo("flaws", catalogue)?.facts).toEqual(["Flaws pay out at most 5 XP in all."]);
    expect(categoryInfo("merits", undefined)?.facts).toEqual([]);
  });

  it("gives nothing for a category with no words", () => {
    expect(categoryInfo("techniques", catalogue)).toBeNull();
  });
});

describe("choiceInfo", () => {
  it("covers the choices in the page title, and only those", () => {
    for (const key of ["clan", "archetype", "sect", "faction"]) expect(choiceInfo(key)).toBeTruthy();
    expect(choiceInfo("skills")).toBeNull();
  });
});
