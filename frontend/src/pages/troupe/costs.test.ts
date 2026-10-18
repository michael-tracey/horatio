import { describe, expect, it } from "vitest";
import type { CostOut } from "../../api/types";
import { overlaps, parseTable, priceAt } from "./costs";

const cost = (overrides: Partial<CostOut>): CostOut => ({
  id: null,
  category: "skills",
  trait: null,
  condition: null,
  condition_text: null,
  price_text: "",
  scheme: "per_dot",
  rate: 1,
  table: null,
  text: null,
  page: null,
  house: false,
  replaced: false,
  ...overrides,
});

describe("priceAt", () => {
  it("prices each scheme as the backend does", () => {
    expect(priceAt({ scheme: "per_dot", rate: 3, table: null }, 4)).toBe(12);
    expect(priceAt({ scheme: "progressive", rate: 2, table: null }, 3)).toBe(12);
    expect(priceAt({ scheme: "fixed", rate: 7, table: null }, 3)).toBe(7);
    expect(priceAt({ scheme: "table", rate: null, table: [1, 4, 6] }, 2)).toBe(5);
    expect(priceAt({ scheme: "free", rate: null, table: null }, 3)).toBe(0);
  });

  it("has no price where none can be had", () => {
    expect(priceAt({ scheme: "not_allowed", rate: null, table: null }, 1)).toBeNull();
    expect(priceAt({ scheme: "table", rate: null, table: [1, 4] }, 3)).toBeNull();
    expect(priceAt({ scheme: "per_dot", rate: null, table: null }, 1)).toBeNull();
  });
});

describe("overlaps", () => {
  const book = [
    cost({}),
    cost({ condition: { generation: 1 } }),
    cost({ category: "merits", trait: "Path of Blood", condition: { clan_family: "Assamite" } }),
    cost({ category: "merits" }),
    cost({ category: "merits", trait: "Lucky" }),
  ];

  it("replaces only what is no more specific than the new price", () => {
    const { replaces, stillApplies } = overlaps({ category: "skills", trait: null, condition: null }, book);
    expect(replaces).toEqual([book[0]]);
    expect(stillApplies).toEqual([book[1]]);
    // A category price leaves the rule set's price for one trait in it.
    expect(overlaps({ category: "merits", trait: null, condition: null }, book).stillApplies).toEqual([book[2], book[4]]);
  });

  it("lets a price for one merit replace the category, but not a clan's price for it", () => {
    const { replaces, stillApplies } = overlaps({ category: "merits", trait: "Path of Blood", condition: null }, book);
    expect(replaces).toEqual([book[3]]);
    expect(stillApplies).toEqual([book[2]]);
  });

  it("replaces a rule set price given the same condition", () => {
    const { replaces } = overlaps({ category: "skills", trait: null, condition: { generation: 1 } }, book);
    expect(replaces).toEqual([book[1]]);
  });

  it("leaves out prices for other conditions", () => {
    const disciplines = [
      cost({ category: "disciplines", condition: { in_clan: true } }),
      cost({ category: "disciplines", condition: { in_clan: false, generation: { lt: 5 } } }),
    ];
    expect(overlaps({ category: "disciplines", trait: null, condition: { in_clan: true } }, disciplines)).toEqual({
      replaces: [disciplines[0]],
      stillApplies: [],
    });
  });
});

describe("parseTable", () => {
  it("reads numbers separated by commas or spaces", () => {
    expect(parseTable("1, 4 6")).toEqual([1, 4, 6]);
    expect(parseTable("1, two")).toBeNull();
    expect(parseTable(" ")).toBeNull();
  });
});
