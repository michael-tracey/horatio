import { describe, expect, it } from "vitest";
import type { PlayView, PowerSwitch, PowerUse } from "../../api/types";
import { applyChange } from "./tracker";
import { plainUse } from "./UsePower";
import { canPay, costText, effectTaps, ghouls, offered, type UseView } from "./uses";

type Mark = "normal" | "aggravated";

function view(marks: Mark[] = [], overrides: Partial<UseView> = {}): UseView {
  return {
    blood_name: "Blood",
    panels: { beast: true, frenzy: true, morality: true, generation: true, feed: true },
    blood: { value: 6, most: 10, start: 10 },
    willpower: { value: 4, most: 6, start: 6 },
    health: {
      levels: [
        { name: "Healthy", boxes: 3 },
        { name: "Injured", boxes: 3 },
        { name: "Incapacitated", boxes: 3 },
      ],
      marks,
      stamina_focus: false,
    },
    beast: { value: 0, most: 5, start: 0 },
    powers: [],
    retainers: [],
    ...overrides,
  };
}

function use(overrides: Partial<PowerUse>): PowerUse {
  return { label: "Use", cost: null, half: false, heal: null, convert: 0, convert_all: false, mend: 0, gains: [], over: false, beast: 0, retainer: 0, animal: false, when: null, once: null, note: null, page: null, target: "self", summon: null, summon_all: false, spends: false, ...overrides };
}

const blood = (amount: number) => ({ tracker: "blood" as const, amount });

/** The marks after the taps, applied as the server applies them. */
function after(v: UseView, taps: ReturnType<typeof effectTaps>): { marks: Mark[]; blood: number; willpower: number; beast: number } {
  const copy = structuredClone(v) as unknown as PlayView;
  for (const t of taps) applyChange(copy, t.tracker!, t.amount!, t.damage ?? null);
  return { marks: copy.health.marks as Mark[], blood: copy.blood.value, willpower: copy.willpower.value, beast: copy.beast.value };
}

describe("a use's taps (issue #825)", () => {
  it("spends its cost, naming the power, then heals the damage it says", () => {
    const corpore = use({ label: "Heal 1 normal", cost: blood(1), heal: { damage: "normal", amount: 1 } });
    const taps = effectTaps(view(["normal", "aggravated", "normal"]), corpore, "Corpore Sano");
    expect(taps[0]).toEqual({ kind: "change", tracker: "blood", amount: -1, note: "Corpore Sano" });
    expect(after(view(["normal", "aggravated", "normal"]), taps)).toMatchObject({ marks: ["normal", "aggravated"], blood: 5 });
  });

  it("changes nothing, and spends nothing, with no damage of its kind to heal", () => {
    const repair = use({ cost: { tracker: "blood", amount: 2 }, heal: { damage: "aggravated", amount: 1 } });
    expect(effectTaps(view(["normal"]), repair, "Fortitude: Repair the Undead Flesh")).toEqual([]);
  });

  it("can't be used without the Blood to pay for it", () => {
    const repair = use({ cost: blood(2), heal: { damage: "aggravated", amount: 1 } });
    expect(effectTaps(view(["aggravated"], { blood: { value: 1, most: 10, start: 10 } }), repair, "Repair")).toEqual([]);
  });

  it("heals the worst first: aggravated, then normal (Moment of Reflection's third use)", () => {
    const third = use({ cost: blood(1), heal: { damage: "worst", amount: 2 } });
    expect(after(view(["normal", "aggravated", "normal"]), effectTaps(view(["normal", "aggravated", "normal"]), third, "Moment")).marks).toEqual(["normal"]);
  });

  it("heals every box (King's Blessing)", () => {
    const blessing = use({ cost: blood(3), heal: { damage: "all", amount: 0 } });
    expect(after(view(["normal", "aggravated", "aggravated"]), effectTaps(view(["normal", "aggravated", "aggravated"]), blessing, "King's Blessing"))).toMatchObject({
      marks: [],
      blood: 3,
    });
  });

  it("turns every aggravated box to normal (Second Wind)", () => {
    const wind = use({ cost: blood(1), convert_all: true });
    const v = view(["aggravated", "normal", "aggravated"]);
    const { marks } = after(v, effectTaps(v, wind, "Second Wind"));
    expect(marks.length).toBe(3);
    expect(marks.every((m) => m === "normal")).toBe(true);
  });

  it("mends aggravated to normal, or with none heals normal (Cocoon)", () => {
    const minute = use({ mend: 1 });
    expect(after(view(["aggravated", "normal"]), effectTaps(view(["aggravated", "normal"]), minute, "Cocoon")).marks).toEqual(["normal", "normal"]);
    expect(after(view(["normal", "normal"]), effectTaps(view(["normal", "normal"]), minute, "Cocoon")).marks).toEqual(["normal"]);
  });

  it("gains Blood and Willpower, never past the pool (Harvest Despair)", () => {
    const harvest = use({ gains: [{ tracker: "willpower", amount: 1 }, blood(2)] });
    const v = view([], { blood: { value: 9, most: 10, start: 10 } });
    const taps = effectTaps(v, harvest, "Harvest Despair");
    expect(taps).toEqual([
      { kind: "change", tracker: "willpower", amount: 1 },
      { kind: "change", tracker: "blood", amount: 1 },
    ]);
    expect(effectTaps(view([], { blood: { value: 10, most: 10, start: 10 }, willpower: { value: 6, most: 6, start: 6 } }), harvest, "Harvest Despair")).toEqual([]);
  });

  it("keeps Mantle of Sutekh's tithes past the pool while it lasts, and only those (#854)", () => {
    const tithe = use({ gains: [blood(1)], over: true, when: "Mantle of Sutekh" });
    const harvest = use({ gains: [blood(2)] });
    const mantle = (on: boolean) => ({ key: "Mantle of Sutekh", on, blood_over: true }) as UseView["powers"][number];
    const full = view([], { blood: { value: 10, most: 10, start: 10 }, powers: [mantle(true)] });
    const taps = effectTaps(full, tithe, "Serpentis: Mantle of Sutekh");
    expect(taps).toEqual([{ kind: "change", tracker: "blood", amount: 1 }]);
    expect(after(full, taps).blood).toBe(11);
    // Other Blood gained still stops at the pool.
    expect(effectTaps(full, harvest, "Harvest Despair")).toEqual([]);
    // With the Mantle off, a tithe at a full pool changes nothing.
    expect(effectTaps(view([], { blood: { value: 10, most: 10, start: 10 }, powers: [mantle(false)] }), tithe, "Serpentis: Mantle of Sutekh")).toEqual([]);
  });

  it("takes a Beast trait for a retest (Feed the Blighted Wolf)", () => {
    const wolf = use({ beast: 1 });
    expect(effectTaps(view(), wolf, "Feed the Blighted Wolf")).toEqual([{ kind: "change", tracker: "beast", amount: 1 }]);
  });

  it("spends half the Blood held, rounded down, and needs 2 (Indestructible)", () => {
    const indestructible = use({ cost: blood(0), half: true, heal: { damage: "asked", amount: 0 } });
    const v = view(["normal", "aggravated", "normal"], { blood: { value: 7, most: 10, start: 10 } });
    expect(costText(v, indestructible)).toBe("half your Blood (3)");
    const taps = effectTaps(v, indestructible, "Fortitude: Indestructible", { asked: { normal: 1, aggravated: 1 } });
    expect(after(v, taps)).toMatchObject({ marks: ["normal"], blood: 4 });
    expect(canPay(view([], { blood: { value: 1, most: 10, start: 10 } }), indestructible)).toBe(false);
  });

  it("moves damage onto an animal ghoul Retainer for a Beast trait (Beast's Vigor, #854)", () => {
    const vigor = use({ retainer: 3, animal: true, beast: 1, when: "Beast's Vigor" });
    const hound = { key: "retainer:Hound", name: "Hound", animal: true, health: { value: 2, most: 3, start: 3 }, blood: { value: 1, most: 1, start: 1 } };
    const butler = { ...hound, key: "retainer:Butler", name: "Butler", animal: false };
    const v = view(["aggravated", "normal", "normal"], { retainers: [hound, butler], powers: [] });
    expect(offered(v, vigor)).toBe(false);
    // Only the animal ghoul takes the damage; a human ghoul isn't offered.
    expect(ghouls(v, vigor).map((r) => r.name)).toEqual(["Hound"]);
    expect(effectTaps(v, vigor, "Beast's Vigor", { retainer: "retainer:Butler" })).toEqual([]);
    const taps = effectTaps(v, vigor, "Beast's Vigor", { retainer: "retainer:Hound" });
    expect(taps).toContainEqual({ kind: "change", tracker: "retainer:Hound/health", amount: -2 });
    expect(after(v, taps)).toMatchObject({ marks: ["normal"], beast: 1 });
  });

  it("is offered only while its switch is on (Cocoon, Mantle of Sutekh)", () => {
    const tithe = use({ gains: [blood(1)], when: "Mantle of Sutekh" });
    const switched = (on: boolean) => view([], { powers: [{ key: "Mantle of Sutekh", on } as UseView["powers"][number]] });
    expect(offered(switched(false), tithe)).toBe(false);
    expect(offered(switched(true), tithe)).toBe(true);
  });
});

describe("a use that calls up allies (issue #827)", () => {
  const ally = (n: number, out = false) => ({ key: `ally:Arms#${n}`, name: `Arm ${n}`, out, order: out ? n : 0, health: { value: 4, most: 4, start: 4 }, blood: null });
  const summons = (outs: boolean[]): UseView["summons"] => [
    { key: "Arms", name: "Arm of the Abyss", origin: "Obtenebration 3", page: "pp. 148-149", note: "", most: outs.length, allies: outs.map((o, i) => ally(i + 1, o)) },
  ];

  it("calls up every one not out with summon_all, after its cost", () => {
    const raise = use({ cost: blood(1), summon: "Arms", summon_all: true });
    const v = view([], { summons: summons([false, true, false]) });
    expect(effectTaps(v, raise, "Arms of the Abyss")).toEqual([
      { kind: "change", tracker: "blood", amount: -1, note: "Arms of the Abyss" },
      { kind: "change", tracker: "ally:Arms#1", amount: 1 },
      { kind: "change", tracker: "ally:Arms#3", amount: 1 },
    ]);
  });

  it("calls up one at a time otherwise, and is off when all are out", () => {
    const one = use({ cost: blood(1), summon: "Arms" });
    expect(effectTaps(view([], { summons: summons([true, false]) }), one, "Shambling Hordes")).toContainEqual({ kind: "change", tracker: "ally:Arms#2", amount: 1 });
    expect(effectTaps(view([], { summons: summons([true, true]) }), one, "Shambling Hordes")).toEqual([]);
  });

  it("calls an ally up fresh, takes its damage only while out, and dismisses it", () => {
    const v = { ...view(), summons: summons([false, false]) } as unknown as PlayView;
    v.summons![0]!.allies[0]!.health!.value = 1;
    expect(applyChange(v, "ally:Arms#1/health", -1)).toEqual([1, 1]);
    expect(applyChange(v, "ally:Arms#1", 1)).toEqual([0, 1]);
    expect(v.summons![0]!.allies[0]!.health!.value).toBe(4);
    expect(applyChange(v, "ally:Arms#1/health", -3)).toEqual([4, 1]);
    expect(applyChange(v, "ally:Arms#1", -1)).toEqual([1, 0]);
    expect(v.summons![0]!.allies[0]!.out).toBe(false);
  });
});

describe("a use that only spends, while an option is picked (#876)", () => {
  it("reforms Bonecraft's body weapon for 1 Blood, while Body Weaponry is picked", () => {
    const reform = use({ label: "Reform the body weapon", cost: { tracker: "blood", amount: 1 }, spends: true, when: "Bonecraft/Body Weaponry" });
    const crafted = (picked: string[]) => ({ key: "Bonecraft", on: true, picked }) as unknown as PowerSwitch;
    expect(offered({ powers: [crafted(["Body Weaponry"])] }, reform)).toBe(true);
    expect(offered({ powers: [crafted(["Extra Limbs"])] }, reform)).toBe(false);
    expect(effectTaps(view(), reform, "Bonecraft")).toEqual([{ kind: "change", tracker: "blood", amount: -1, note: "Bonecraft" }]);
    // It waits on a switch, so Bonecraft's own Use stays beside it.
    expect(plainUse({ name: "Bonecraft", cost: { tracker: "blood", amount: 1 }, uses: [reform] })).toBe(true);
    expect(plainUse({ name: "Corpore Sano", cost: { tracker: "blood", amount: 1 }, uses: [use({ cost: { tracker: "blood", amount: 1 }, heal: { damage: "normal", amount: 1 } })] })).toBe(false);
  });
});
