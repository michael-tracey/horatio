import { describe, expect, it } from "vitest";
import type { PoolModifier, TestPool } from "../../api/types";
import { appliesTo, attackGlance, breakdown, damageShort, damageText, damageTotal, describe as describeModifier, defenceGlance, describePools, fightFirst, grouped, qualityText, showing, switchedDamage, topAttacks, total, trackersOf, variantNow, variantsOn, variantText, withAttribute } from "./pools";

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

  it("shows a power's own test only while its switch is on", () => {
    const assault = pool({ key: "power:Psychic Assault", name: "Psychic Assault", switch: "Psychic Assault" });
    const brawl = pool({ key: "attack:Brawl", name: "Unarmed attack" });
    expect(showing([brawl, assault], []).map((p) => p.key)).toEqual(["attack:Brawl"]);
    expect(showing([brawl, assault], ["Psychic Assault"]).map((p) => p.key)).toEqual(["attack:Brawl", "power:Psychic Assault"]);
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
    reducible: true,
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

  it("says a power's own damage plainly, and when nothing reduces it", () => {
    const assault = melee({ kind: "power", parts: [{ label: "Psychic Assault", value: 4 }], total: 4, reducible: false });
    expect(damageText(assault)).toBe("Damage 4, nothing reduces it · exceptional 5");
    expect(damageShort(assault)).toBe("4 damage, nothing reduces it (5 exceptional)");
    const bolt = melee({ kind: "power", type: "aggravated", parts: [{ label: "Chronoton Bolt", value: 2 }], total: 2 });
    expect(damageText(bolt)).toBe("Aggravated damage 2 · exceptional 3");
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
      reducible: true,
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

describe("defences that aren't a flat bonus (issue #602)", () => {
  // Mental 3 + Willpower, with Rampart of Faith's variant and Rockheart's Physical 5 + Survival 2 instead.
  const mental = pool({
    key: "defense:Mental",
    name: "Resisting Mental powers",
    group: "Defence",
    parts: [{ label: "Mental", value: 3 }],
    total: 3,
    adds_willpower: true,
    variants: [
      { when: "For 1 Blood", total: 3, parts: [], instead: false, tracked: [{ label: "Rampart of Faith", tracks: "morality_less_beast" }], qualities: [] },
      {
        when: "Instead, with Rockheart",
        total: 7,
        parts: [
          { label: "Physical", value: 5 },
          { label: "Survival", value: 2 },
        ],
        instead: true,
        tracked: [],
        qualities: [],
      },
    ],
    switched: [
      { switch: "Horrid Form", label: "Mental (Horrid Form)", value: -3, attribute: "Mental", most: null },
      { switch: "Ward", label: "Ward", value: 1, attribute: null, most: null },
    ],
  });
  const [rampart, rockheart] = mental.variants as [TestPool["variants"][number], TestPool["variants"][number]];

  it("adds Morality minus Beast traits now to the pool with Willpower, for Rampart of Faith", () => {
    const now = variantNow(mental, rampart, 4, [], [], { morality: 5, beast: 2 });
    expect(now.total).toBe(3 + 4 + 3);
    expect(variantText(now)).toBe("+3 Rampart of Faith");
    // It follows the trackers, and never takes away.
    expect(variantNow(mental, rampart, 4, [], [], { morality: 4, beast: 0 }).total).toBe(11);
    expect(variantNow(mental, rampart, 4, [], [], { morality: 1, beast: 3 }).total).toBe(7);
    expect(variantNow(mental, rampart, 4).total).toBe(7);
    // And counts what is on, as the pool does.
    expect(variantNow(mental, rampart, 4, [], ["Horrid Form"], { morality: 5, beast: 2 }).total).toBe(0 + 4 + 3);
  });

  it("adds current Derangement traits for Manic Episode (#820, Vol. 2 Issue 1 p. 71)", () => {
    const initiative = pool({ key: "initiative", name: "Initiative", group: "Combat", parts: [{ label: "Physical", value: 4 }], total: 4, adds_willpower: false, variants: [] });
    const manic = { when: "With Celerity active", total: 4, parts: [], instead: false, tracked: [{ label: "Manic Episode", tracks: "derangements" as const }], qualities: [] };
    const now = variantNow(initiative, manic, 0, [], [], { morality: 5, beast: 2, derangements: 3 });
    expect(now.total).toBe(7);
    expect(variantText(now)).toBe("+3 Manic Episode");
    // A Play View kept from before has no Derangement traits to count.
    expect(variantNow(initiative, manic, 0, [], [], { morality: 5, beast: 2 }).total).toBe(4);
  });

  it("counts Physical + Survival without Willpower, for Rockheart", () => {
    const now = variantNow(mental, rockheart, 6);
    expect(now.total).toBe(7);
    expect(variantText(now)).toBe("Physical 5 + Survival 2");
    // A defence modifier or one on Physical counts; one on Mental, and Horrid Form's Mental, don't.
    const mods = [
      { id: "a", label: "Steady", amount: 1, pools: "defense", when: "", on: true },
      { id: "b", label: "Brawny", amount: 2, pools: "Physical", when: "", on: true },
      { id: "c", label: "Sharp", amount: 2, pools: "Mental", when: "", on: true },
    ];
    expect(variantNow(mental, rockheart, 6, mods, ["Horrid Form", "Ward"]).total).toBe(7 + 1 + 2 + 1);
  });

  it("reads Morality, Beast traits and Derangement traits from the Play View", () => {
    expect(trackersOf({ morality: { value: 4 }, beast: { value: 1 } })).toEqual({ morality: 4, beast: 1, derangements: 0, charges: {} });
    expect(trackersOf({ morality: null, beast: { value: 0 }, derangements: { value: 2 } })).toEqual({ morality: 0, beast: 0, derangements: 2, charges: {} });
  });
});

describe("an attack against your hunted target (issue #613)", () => {
  const brutal = { name: "Brutal", play: "Win on the larger pool: exceptional success", page: "p. 516" };
  // Physical 6 + Brawl 3, with Killer Instincts' line for the target it hunts, and Celerity's +2 while on.
  const brawl = pool({
    key: "attack:Brawl",
    name: "Unarmed attack",
    parts: [
      { label: "Physical", value: 6 },
      { label: "Brawl", value: 3 },
    ],
    variants: [{ when: "Against your hunted target", total: 11, parts: [{ label: "Accurate", value: 2 }], instead: false, tracked: [], switch: "Killer Instincts", qualities: [brutal] }],
    switched: [{ switch: "Celerity", label: "Celerity", value: 2, attribute: null, most: null }],
  });
  const [hunted] = brawl.variants as [TestPool["variants"][number]];

  it("shows the line only while Killer Instincts is on, and leaves the attack's total alone", () => {
    expect(variantsOn(brawl, [])).toEqual([]);
    expect(variantsOn(brawl, ["Celerity"])).toEqual([]);
    expect(variantsOn(brawl, ["Killer Instincts"])).toEqual([hunted]);
    expect(total(brawl, 0, [], ["Killer Instincts"])).toBe(9);
  });

  it("counts +2 Accurate on what the attack counts now, and gives Brutal", () => {
    const now = variantNow(brawl, hunted, 0, [], ["Killer Instincts"]);
    expect([now.when, now.total, variantText(now)]).toEqual(["Against your hunted target", 11, "+2 Accurate"]);
    expect(now.qualities).toEqual([brutal]);
    expect(variantNow(brawl, hunted, 0, [{ id: "a", label: "Sharp", amount: 1, pools: "attack", when: "", on: true }], ["Killer Instincts", "Celerity"]).total).toBe(9 + 2 + 2 + 1);
    expect(qualityText(brutal)).toBe("Brutal: win on the larger pool: exceptional success (p. 516)");
  });

  it("shows every variant from a Play View kept from before, which has no switch", () => {
    const old = pool({ variants: [{ when: "For 1 Blood", total: 9, parts: [], instead: false, tracked: [] } as unknown as TestPool["variants"][number]] });
    expect(variantsOn(old, [])).toHaveLength(1);
    expect(variantNow(old, old.variants[0]!, 0).qualities).toEqual([]);
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
      reducible: true,
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
    // Armour that differs by attack (#599): each after Dodge.
    const marble = [
      { id: "a", label: "Flesh of Marble: Ballistic", amount: 3, pools: "pool:dodge", when: "against firearms", on: true, situational: true },
      { id: "b", label: "Flesh of Marble: Ballistic", amount: 1, pools: "pool:dodge", when: "against Brawl, Melee and thrown weapons", on: true, situational: true },
    ];
    expect(defenceGlance([pool({}), social], 3, marble)).toEqual(["Dodge 9 (12 against firearms, 10 against Brawl, Melee and thrown weapons)", "vs Social 7"]);
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
