import { describe, expect, it } from "vitest";
import { healthRows } from "./health";

const level = (name: string, rating: number | null) => ({ category: "health_levels", name, rating });

describe("healthRows", () => {
  it("lists Healthy, Injured and Incapacitated in the paper sheet's order", () => {
    const rows = healthRows([level("Incapacitated", 3), level("Healthy", 3), level("Injured", 3)]);
    expect(rows.map((r) => [r.name, r.boxes])).toEqual([
      ["Healthy", 3],
      ["Injured", 3],
      ["Incapacitated", 3],
    ]);
  });

  it("gives each row the sheet's count, so merits and flaws change it", () => {
    // Rugged adds one to each; Permanent Wound takes two Healthy levels.
    const rows = healthRows([level("Healthy", 2), level("Injured", 4), level("Incapacitated", 4)]);
    expect(rows.map((r) => r.boxes)).toEqual([2, 4, 4]);
  });

  it("keeps a row with no levels left, with no boxes", () => {
    const rows = healthRows([level("Healthy", 0), level("Injured", 3)]);
    expect(rows.map((r) => [r.name, r.boxes])).toEqual([
      ["Healthy", 0],
      ["Injured", 3],
      ["Incapacitated", 0],
    ]);
    expect(rows[2]!.trait).toBeUndefined();
  });

  it("ignores other categories and puts levels a rule set adds last", () => {
    const rows = healthRows([
      { category: "willpower_sources", name: "Willpower", rating: 6 },
      level("Torpor", 1),
      level("Healthy", 3),
    ]);
    expect(rows.map((r) => r.name)).toEqual(["Healthy", "Injured", "Incapacitated", "Torpor"]);
  });
});
