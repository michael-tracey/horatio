import { describe, expect, it } from "vitest";
import type { SetupOut } from "../../api/types";
import { differentAreas } from "./SetupTab";

const book: SetupOut = {
  described: true,
  profile: true,
  staff: 1,
  cycles: 1,
  checks: 0,
  checks_total: 450,
  costs: 0,
  starting: 0,
  actions: 0,
  house_traits: 0,
  other: 0,
  connectors: [],
};

describe("the parts of the rules a troupe plays differently (#786)", () => {
  it("has none while everything plays as the book has it", () => {
    expect(differentAreas(book, "/troupes/t")).toEqual([]);
  });

  it("names each part that differs, linked into its rules, and leaves out the rest", () => {
    const areas = differentAreas({ ...book, checks: 3, costs: 1, house_traits: 2, other: 1 }, "/troupes/t");
    expect(areas).toEqual([
      { label: "Checks", text: "3 of 450 played differently", to: "/troupes/t/house-rules/checks" },
      { label: "Costs", text: "1 house price", to: "/troupes/t/house-rules/costs" },
      { label: "House merits and flaws", text: "2 of the troupe's own", to: "/troupes/t/house-rules/house-traits" },
      { label: "Other house rules", text: "1 setting unlike the book", to: "/troupes/t/house-rules" },
    ]);
  });

  it("counts house rules in starting points and downtime actions", () => {
    const areas = differentAreas({ ...book, starting: 1, actions: 4 }, "/troupes/t");
    expect(areas.map((a) => `${a.label}: ${a.text}`)).toEqual(["Starting points: 1 house rule", "Downtime actions: 4 house rules"]);
  });
});
