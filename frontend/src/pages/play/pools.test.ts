import { describe, expect, it } from "vitest";
import type { PoolModifier, TestPool } from "../../api/types";
import { appliesTo, attackGlance, breakdown, damageShort, damageText, damageTotal, describe as describeModifier, defenceGlance, describePools, fightFirst, grouped, switchedDamage, topAttacks, total, withAttribute } from "./pools";

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
  switched: [],
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
    switched: [],
    parts: [{ label: "melee", value: 1 }],
    total: 1,
    exceptional: 1,
    notes: [],
    ...over,
  });

  it("shows the base for the attack type and its exceptional success", () => {
    expect(damageText(melee())).toBe("Damage 1 (melee) · exceptional 2");
    expect(damageText(melee({ kind: "firearms", parts: [{ label: "firearms", value: 2 }], total: 2 }))).toBe("Damage 2 (firearms) · exceptional 3");
  });

  it("shows what Potence adds, and aggravated damage where a power makes it so", () => {
    const might = melee({ total: 2, parts: [{ label: "melee", value: 1 }, { label: "Might", value: 1 }] });
    expect(damageText(might)).toBe("Damage 2 (1 melee + 1 Might) · exceptional 3");
    const intensity = { ...might, exceptional: 2 };
    expect(damageText(intensity)).toBe("Damage 2 (1 melee + 1 Might) · exceptional 4");
    expect(damageShort(intensity)).toBe("2 damage (4 exceptional)");
    expect(damageText(melee({ type: "aggravated" }))).toBe("Aggravated damage 1 (melee) · exceptional 2");
  });

  it("leaves a seam for damage a modifier adds", () => {
    expect(damageText(melee(), [{ label: "brass knuckles", value: 1 }])).toBe("Damage 2 (1 melee + 1 brass knuckles) · exceptional 3");
    expect(damageTotal(melee(), [{ label: "brass knuckles", value: 1 }])).toBe(2);
  });
});

describe("forms and powers switched on", () => {
  const brawl = pool({
    key: "attack:Brawl",
    name: "Unarmed attack",
    parts: [
      { label: "Physical", value: 5 },
      { label: "Brawl", value: 3 },
    ],
    total: 8,
    switched: [
      { switch: "fight form", label: "Shape of the Beast", value: 2, attribute: null, most: null },
      { switch: "flight form", label: "Physical (flight form)", value: 0, attribute: "Physical", most: 3 },
      { switch: "Celerity", label: "Alacrity", value: 0, attribute: null, most: null },
    ],
  });

  it("adds what a form gives only while it is on, with the reason", () => {
    expect(total(brawl, 0)).toBe(8);
    expect(total(brawl, 0, [], ["fight form"])).toBe(10);
    expect(breakdown(brawl, 0, [], ["fight form"])).toBe("Physical 5 + Brawl 3 + Shape of the Beast 2");
  });

  it("counts an attribute a form changes as it counts now", () => {
    expect(total(brawl, 0, [], ["flight form"])).toBe(6);
    expect(breakdown(brawl, 0, [], ["flight form"])).toBe("Physical (flight form) 3 + Brawl 3");
    const weak = pool({ ...brawl, parts: [{ label: "Physical", value: 2 }, { label: "Brawl", value: 3 }], total: 5 });
    expect(total(weak, 0, [], ["flight form"])).toBe(5); // reduced to 3, never raised
  });

  it("goes with the player's own modifiers", () => {
    const fame = { id: "m", label: "Rage", amount: 1, pools: "attack", when: "", on: true };
    expect(total(brawl, 0, [fame], ["fight form"])).toBe(11);
    expect(breakdown(brawl, 0, [fame], ["fight form"])).toBe("Physical 5 + Brawl 3 + Shape of the Beast 2 + Rage 1");
  });

  it("makes damage aggravated through the damage seam while a power is on", () => {
    const damage = {
      kind: "unarmed",
      type: "normal" as const,
      parts: [{ label: "unarmed", value: 1 }],
      total: 1,
      exceptional: 1,
      notes: [],
      switched: [
        { switch: "Feral Claws", label: "Feral Claws", amount: 0, exceptional: 0, type: "aggravated" as const },
        { switch: "The Fourth Horseman", label: "The Fourth Horseman", amount: 1, exceptional: 0, type: "normal" as const },
      ],
    };
    expect(damageText(damage, switchedDamage(damage, []))).toBe("Damage 1 (unarmed) · exceptional 2");
    expect(damageText(damage, switchedDamage(damage, ["Feral Claws"]))).toBe("Damage 1 (unarmed), aggravated by Feral Claws · exceptional 2");
    const both = switchedDamage(damage, ["Feral Claws", "The Fourth Horseman"]);
    expect(damageText(damage, both)).toBe("Damage 2 (1 unarmed + 1 The Fourth Horseman), aggravated by Feral Claws · exceptional 3");
  });
});

describe("other tests", () => {
  const intimidation = pool({
    key: "skill:Intimidation",
    name: "Intimidation",
    group: "Other tests",
    parts: [
      { label: "Social", value: 6 },
      { label: "Intimidation", value: 3 },
      { label: "Executioner", value: 1 },
    ],
    total: 10,
    switched: [{ switch: "Horrid Form", label: "Mental (Horrid Form)", value: -3, attribute: "Mental", most: null }],
  });

  it("computes attribute + skill + what changes it, with its arithmetic", () => {
    expect(total(intimidation, 4)).toBe(10);
    expect(breakdown(intimidation, 4)).toBe("Social 6 + Intimidation 3 + Executioner 1");
  });

  it("counts another attribute when the storyteller names one, with the modifiers on it", () => {
    const mental = withAttribute(intimidation, "Mental", 4);
    expect(total(mental, 0)).toBe(8);
    expect(breakdown(mental, 0)).toBe("Mental 4 + Intimidation 3 + Executioner 1");
    expect(total(mental, 0, [], ["Horrid Form"])).toBe(5);
    expect(total(mental, 0, [{ id: "m", label: "Sharp", amount: 2, pools: "Mental", when: "", on: true }])).toBe(10);
    expect(withAttribute(intimidation, "Social", 6)).toBe(intimidation);
  });
});

describe("the Scene view's glance", () => {
  const attack = (name: string, value: number, over: Partial<TestPool> = {}) =>
    pool({
      key: `attack:${name}`,
      name: `${name} attack`,
      parts: [{ label: name, value }],
      total: value,
      ...over,
    });
  const names = (pools: TestPool[]) => pools.map((p) => p.key);

  it("picks the three highest attacks, equal totals in the book's order", () => {
    const pools = [pool({}), attack("Brawl", 7), attack("Melee", 9), attack("Firearms", 7), attack("Athletics", 7)];
    expect(names(topAttacks(pools, 0))).toEqual(["attack:Melee", "attack:Brawl", "attack:Firearms"]);
  });

  it("shows what there is when there are fewer than three, and nothing when there are none", () => {
    expect(names(topAttacks([attack("Brawl", 5), pool({})], 0))).toEqual(["attack:Brawl"]);
    expect(topAttacks([pool({})], 0)).toEqual([]);
  });

  it("follows a form that is on", () => {
    const brawl = attack("Brawl", 5, {
      switched: [
        {
          switch: "fight form",
          label: "Shape of the Beast",
          value: 3,
          attribute: null,
          most: null,
        },
      ],
    });
    const pools = [brawl, attack("Melee", 7)];
    expect(names(topAttacks(pools, 0))).toEqual(["attack:Melee", "attack:Brawl"]);
    expect(names(topAttacks(pools, 0, [], ["fight form"]))).toEqual(["attack:Brawl", "attack:Melee"]);
  });

  it("says an attack with its damage, and the defences in a line", () => {
    const damage = {
      kind: "unarmed",
      type: "normal" as const,
      parts: [{ label: "unarmed", value: 1 }],
      total: 1,
      exceptional: 1,
      notes: [],
      switched: [],
    };
    expect(attackGlance(attack("Unarmed", 9, { damage }), 0)).toBe("Unarmed 9 (1 dmg)");
    expect(attackGlance(attack("Thrown", 4), 0)).toBe("Thrown 4");
    const social = pool({
      key: "defense:Social",
      name: "Resisting Social powers",
      group: "Defence",
      parts: [{ label: "Social", value: 4 }],
      total: 4,
      adds_willpower: true,
    });
    expect(defenceGlance([pool({}), social], 3)).toEqual(["Dodge 9", "vs Social 7"]);
  });

  it("puts Combat and Defence before the other groups", () => {
    const groups: [string, TestPool[]][] = [
      ["Disciplines", []],
      ["Defence", []],
      ["Other", []],
      ["Combat", []],
    ];
    expect(fightFirst(groups).map(([g]) => g)).toEqual(["Combat", "Defence", "Disciplines", "Other"]);
  });
});
