import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "../../api/types";
import { clanFamilies, dotCategories, hasRating, newBlock, retype, traitNames, typeOf } from "./houseEffects";

const category = (key: string, over: Partial<CatalogueOut["categories"][number]> = {}) => ({
  key,
  name: key[0]!.toUpperCase() + key.slice(1),
  group: "",
  rated: true,
  max_rating: null,
  derived: false,
  ...over,
});
const trait = (category: string, name: string, over: Partial<CatalogueOut["traits"][number]> = {}) => ({
  category,
  name,
  description: null,
  page_reference: null,
  fixed_rating: null,
  house_rule: null,
  in_clan: null,
  attribute: null,
  ...over,
});

const catalogue = {
  splat: "vampire",
  name: "MET",
  categories: [
    category("clan", { rated: false }),
    category("skills"),
    category("backgrounds"),
    category("health_levels", { derived: true }),
    category("merits"),
    category("lore_specializations", { specializes: { category: "skills", name: "Lore" } }),
  ],
  traits: [
    trait("clan", "Brujah"),
    trait("clan", "Brujah: True Brujah"),
    trait("clan", "Ventrue"),
    trait("skills", "Lore"),
    trait("backgrounds", "Resources"),
    trait("health_levels", "Healthy"),
    trait("merits", "Old Money", { fixed_rating: 2 }),
    trait("merits", "Rugged", { fixed_rating: 2 }),
    trait("lore_specializations", "Sabbat"),
  ],
} as CatalogueOut;

describe("house effect blocks", () => {
  it("offers dots only in rated traits bought dot by dot, and merits only to give", () => {
    expect(dotCategories(catalogue, "free").map((c) => c.key)).toEqual(["skills", "backgrounds", "merits"]);
    expect(dotCategories(catalogue, "raise").map((c) => c.key)).toEqual(["skills", "backgrounds"]);
  });

  it("never lists the merit as its own effect", () => {
    expect(traitNames(catalogue, "merits", { category: "merits", name: "Old Money" })).toEqual(["Rugged"]);
  });

  it("puts a clan's bloodlines with it", () => {
    expect(clanFamilies(catalogue)).toEqual(["Brujah", "Ventrue"]);
  });

  it("asks a rating only of a trait bought dot by dot", () => {
    expect(hasRating(catalogue, "backgrounds", "Resources")).toBe(true);
    expect(hasRating(catalogue, "merits", "Rugged")).toBe(false);
  });

  it("keeps the traits when a block becomes another that lists them", () => {
    const free = { ...newBlock("free"), names: ["Resources"] };
    expect(retype(free, "raise")).toMatchObject({ kind: "raise_max", category: "backgrounds", names: ["Resources"] });
    expect(retype(free, "requires")).toMatchObject({ kind: "requires", names: [] });
    expect(typeOf(newBlock("price"))).toBe("price");
    expect(typeOf(newBlock("health"))).toBe("health");
  });
});
