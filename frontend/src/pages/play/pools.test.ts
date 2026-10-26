import { describe, expect, it } from "vitest";
import type { PoolModifier, TestPool } from "../../api/types";
import { appliesTo, breakdown, damageShort, damageText, damageTotal, describe as describeModifier, describePools, exceptionalText, grouped, total } from "./pools";

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

describe("pool modifiers", () => {
  const social = pool({ key: "defense:Social", name: "Resisting Social powers", group: "Defence", parts: [{ label: "Social", value: 4 }], total: 4, adds_willpower: true });
  const brawl = pool({ key: "attack:Brawl", name: "Unarmed attack", parts: [{ label: "Physical", value: 6 }, { label: "Brawl", value: 2 }], total: 8 });
  const mod = (over: Partial<PoolModifier>): PoolModifier => ({ id: "m", label: "Fame", amount: 2, pools: "Social", when: "", on: true, ...over });

  it("adds a modifier that is on to each pool it applies to, and names it in the breakdown", () => {
    expect(total(social, 3, [mod({})])).toBe(9);
    expect(breakdown(social, 3, [mod({})])).toBe("Social 4 + Willpower 3 + Fame 2");
    expect(total(brawl, 3, [mod({})])).toBe(8);
  });

  it("leaves a modifier that is off out of both", () => {
    expect(total(social, 3, [mod({ on: false })])).toBe(7);
    expect(breakdown(social, 3, [mod({ on: false })])).toBe("Social 4 + Willpower 3");
  });

  it("subtracts a penalty", () => {
    expect(breakdown(brawl, 0, [mod({ label: "Lame", amount: -2, pools: "Physical" })])).toBe("Physical 6 + Brawl 2 − Lame 2");
    expect(total(brawl, 0, [mod({ amount: -2, pools: "Physical" })])).toBe(6);
  });

  it("applies to one pool, a group or all", () => {
    expect(appliesTo(mod({ pools: "attack" }), brawl)).toBe(true);
    expect(appliesTo(mod({ pools: "attack" }), social)).toBe(false);
    expect(appliesTo(mod({ pools: "defense" }), social)).toBe(true);
    expect(appliesTo(mod({ pools: "pool:attack:Brawl" }), brawl)).toBe(true);
    expect(appliesTo(mod({ pools: "pool:dodge" }), brawl)).toBe(false);
    expect(appliesTo(mod({ pools: "all" }), brawl)).toBe(true);
    expect(describeModifier(mod({ when: "against mortals" }), [])).toBe("+2 Social pools, against mortals");
    expect(describePools("pool:attack:Brawl", [brawl])).toBe("Unarmed attack");
  });
});

describe("damage", () => {
  const melee = (over: Partial<NonNullable<TestPool["damage"]>> = {}): NonNullable<TestPool["damage"]> => ({
    kind: "melee",
    type: "normal",
    parts: [{ label: "melee", value: 1 }],
    total: 1,
    exceptional: 1,
    notes: [],
    ...over,
  });

  it("shows the base for the attack type and its exceptional success", () => {
    expect(damageText(melee())).toBe("1 damage: 1 (melee)");
    expect(exceptionalText(melee())).toBe("An exceptional success adds 1 damage, 2 in all.");
    expect(damageText(melee({ kind: "firearms", parts: [{ label: "firearms", value: 2 }], total: 2 }))).toBe("2 damage: 2 (firearms)");
  });

  it("shows what Potence adds, and aggravated damage where a power makes it so", () => {
    const might = melee({ total: 2, parts: [{ label: "melee", value: 1 }, { label: "Might", value: 1 }] });
    expect(damageText(might)).toBe("2 damage: 1 (melee) + 1 (Might)");
    const intensity = { ...might, exceptional: 2 };
    expect(exceptionalText(intensity)).toBe("An exceptional success adds 2 damage, 4 in all.");
    expect(damageShort(intensity)).toBe("2 damage (4 exceptional)");
    expect(damageText(melee({ type: "aggravated" }))).toBe("1 aggravated damage: 1 (melee)");
  });

  it("leaves a seam for damage a modifier adds", () => {
    expect(damageText(melee(), [{ label: "brass knuckles", value: 1 }])).toBe("2 damage: 1 (melee) + 1 (brass knuckles)");
    expect(damageTotal(melee(), [{ label: "brass knuckles", value: 1 }])).toBe(2);
  });
});
