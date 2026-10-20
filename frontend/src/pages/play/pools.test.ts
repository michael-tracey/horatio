import { describe, expect, it } from "vitest";
import type { TestPool } from "../../api/types";
import { breakdown, grouped, total } from "./pools";

const pool = (over: Partial<TestPool>): TestPool => ({
  key: "dodge",
  name: "Dodge",
  group: "Combat",
  parts: [
    { label: "Physical", value: 6 },
    { label: "Dodge", value: 3 },
  ],
  total: 9,
  versus: null,
  adds_willpower: false,
  willpower_floor: 0,
  variants: [],
  notes: [],
  ...over,
});

describe("pools", () => {
  it("adds current Willpower to defence pools only", () => {
    const mental = pool({ key: "defense:Mental", parts: [{ label: "Mental", value: 4 }], total: 4, adds_willpower: true });
    expect(total(mental, 5)).toBe(9);
    expect(breakdown(mental, 5)).toBe("Mental 4 + Willpower 5");
    expect(total(pool({}), 5)).toBe(9);
  });

  it("never counts Willpower below a floor", () => {
    const social = pool({ parts: [{ label: "Social", value: 3 }], total: 3, adds_willpower: true, willpower_floor: 3 });
    expect(total(social, 1)).toBe(6);
  });

  it("shows penalties as subtractions", () => {
    const initiative = pool({
      parts: [
        { label: "Physical", value: 6 },
        { label: "Slow Reactions", value: -5 },
      ],
      total: 1,
    });
    expect(breakdown(initiative, 0)).toBe("Physical 6 − Slow Reactions 5");
  });

  it("keeps the groups in order", () => {
    const found = grouped([pool({ key: "a" }), pool({ key: "b", group: "Defence" }), pool({ key: "c" })]);
    expect(found.map(([g, ps]) => [g, ps.map((p) => p.key)])).toEqual([
      ["Combat", ["a", "c"]],
      ["Defence", ["b"]],
    ]);
  });
});
