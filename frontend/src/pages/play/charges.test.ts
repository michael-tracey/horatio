import { describe, expect, it } from "vitest";
import type { Charge, PlayView, PowerUse } from "../../api/types";
import { chargesFor, fadeTaps } from "./Charges";
import { trackedValue, trackersOf } from "./pools";
import { applyChange, CHARGE, trackerName } from "./tracker";
import { canSpend, effectTaps, spendAmounts, unitsText, type UseView } from "./uses";

const KINETICISM = `${CHARGE}Kineticism`;

function charge(over: Partial<Charge> = {}): Charge {
  return {
    key: KINETICISM,
    name: "Kineticism charges",
    unit: "charge",
    units: "charges",
    most: 5,
    value: 0,
    fades: [
      { label: "Fight over", keep: 0, off: null },
      { label: "Going into a fight", keep: 1, off: null },
    ],
    discipline: "Kineticism",
    power: null,
    other: null,
    note: null,
    page: "Vol. 2, p. 72",
    ...over,
  };
}

function view(charges: Charge[], overrides: Partial<UseView> = {}): UseView {
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
      marks: [],
      stamina_focus: false,
    },
    beast: { value: 0, most: 5, start: 0 },
    powers: [],
    retainers: [],
    charges,
    ...overrides,
  };
}

function use(overrides: Partial<PowerUse>): PowerUse {
  return { label: "Use", cost: null, half: false, heal: null, convert: 0, convert_all: false, mend: 0, gains: [], beast: 0, retainer: 0, when: null, once: null, note: null, page: null, target: "self", charges: null, on: null, animal: false, over: false, ...overrides };
}

const change = (counter: string, over: Record<string, unknown>) => ({ counter, gain: 0, spend: 0, more: false, fill: false, reset: false, ...over });

describe("a power's charges (issue #826)", () => {
  it("stores a charge, never past its most", () => {
    const store = use({ label: "Store a charge", charges: change(KINETICISM, { gain: 1 }) });
    expect(effectTaps(view([charge({ value: 2 })]), store, "Accumulate")).toEqual([{ kind: "change", tracker: KINETICISM, amount: 1 }]);
    expect(effectTaps(view([charge({ value: 5 })]), store, "Accumulate")).toEqual([]);
  });

  it("spends charges only when they're held", () => {
    const redirect = use({ label: "Redirect it", charges: change(KINETICISM, { spend: 2 }) });
    expect(canSpend(view([charge({ value: 1 })]), redirect)).toBe(false);
    expect(effectTaps(view([charge({ value: 1 })]), redirect, "Redirection")).toEqual([]);
    expect(effectTaps(view([charge({ value: 3 })]), redirect, "Redirection")).toEqual([{ kind: "change", tracker: KINETICISM, amount: -2 }]);
  });

  it("lets the player spend as many as they hold (Vengeful Strike)", () => {
    const strike = use({ label: "Unsoakable", charges: change(KINETICISM, { spend: 1, more: true }) });
    expect(spendAmounts(view([charge({ value: 3 })]), strike)).toEqual([1, 2, 3]);
    expect(spendAmounts(view([charge({ value: 0 })]), strike)).toEqual([1]);
    expect(effectTaps(view([charge({ value: 3 })]), strike, "Vengeful Strike", { spend: 2 })).toEqual([{ kind: "change", tracker: KINETICISM, amount: -2 }]);
  });

  it("fills Grace for its Blood, losing what was left, and still spends at full", () => {
    const grace = charge({ key: `${CHARGE}Rayzeel's Grace`, name: "Grace", unit: "Grace", units: "Grace", most: 6, value: 2 });
    const call = use({ label: "Call up Grace", cost: { tracker: "blood", amount: 2 }, charges: change(grace.key, { fill: true }) });
    expect(effectTaps(view([grace]), call, "Rayzeel's Grace")).toEqual([
      { kind: "change", tracker: "blood", amount: -2, note: "Rayzeel's Grace" },
      { kind: "change", tracker: grace.key, amount: 4 },
    ]);
    // Used again at full, its Blood is still spent (Vol. 2 p. 219: what's left goes).
    expect(effectTaps(view([{ ...grace, value: 6 }]), call, "Rayzeel's Grace")).toEqual([{ kind: "change", tracker: "blood", amount: -2, note: "Rayzeel's Grace" }]);
  });

  it("spends a Grace only when it heals something", () => {
    const grace = charge({ key: `${CHARGE}Rayzeel's Grace`, name: "Grace", unit: "Grace", units: "Grace", most: 6, value: 3 });
    const heal = use({ label: "Heal 1 normal", heal: { damage: "normal", amount: 1 }, charges: change(grace.key, { spend: 1 }) });
    expect(effectTaps(view([grace]), heal, "Rayzeel's Grace")).toEqual([]);
    const hurt = view([grace], { health: { ...view([]).health, marks: ["normal"] } });
    expect(effectTaps(hurt, heal, "Rayzeel's Grace")).toEqual([
      { kind: "change", tracker: "health", amount: -1, damage: "normal" },
      { kind: "change", tracker: grace.key, amount: -1 },
    ]);
  });

  it("marks a new target: the stack starts again and the mark goes on", () => {
    const due = charge({ key: `${CHARGE}Reaper's Due`, name: "Reaper's Due", most: 5, value: 3 });
    const mark = use({ label: "Mark them", charges: change(due.key, { reset: true }), on: "Reaper's Due" });
    const off = { key: "Reaper's Due", on: false } as unknown as PlayView["powers"][number];
    expect(effectTaps(view([due], { powers: [off] }), mark, "Reaper's Due")).toEqual([
      { kind: "change", tracker: due.key, amount: -3 },
      { kind: "change", tracker: "power:Reaper's Due", amount: 1 },
    ]);
  });

  it("names amounts in its own words", () => {
    expect(unitsText(charge(), 1)).toBe("1 charge");
    expect(unitsText(charge(), 2)).toBe("2 charges");
  });
});

describe("letting charges go (issue #826)", () => {
  it("empties them when the fight is over, and keeps 1 going into one", () => {
    const [over, into] = charge().fades;
    const held = charge({ value: 3 });
    expect(fadeTaps({ powers: [] }, held, over!)).toEqual([{ kind: "change", tracker: KINETICISM, amount: -3 }]);
    expect(fadeTaps({ powers: [] }, held, into!)).toEqual([{ kind: "change", tracker: KINETICISM, amount: -2 }]);
    expect(fadeTaps({ powers: [] }, charge({ value: 1 }), into!)).toEqual([]);
  });

  it("switches the mark off with the stack", () => {
    const due = charge({ key: `${CHARGE}Reaper's Due`, value: 2 });
    const on = { key: "Reaper's Due", on: true } as unknown as PlayView["powers"][number];
    expect(fadeTaps({ powers: [on] }, due, { label: "Ten minutes up", keep: 0, off: "Reaper's Due" })).toEqual([
      { kind: "change", tracker: due.key, amount: -2 },
      { kind: "change", tracker: "power:Reaper's Due", amount: -1 },
    ]);
  });

  it("finds each counter where the Pools tab shows it", () => {
    const due = charge({ key: `${CHARGE}Reaper's Due`, discipline: "Necromancy: Path of the Graveborn", power: "Reaper's Due" });
    const grace = charge({ key: `${CHARGE}Rayzeel's Grace`, discipline: null, other: "Obeah: Rayzeel's Grace" });
    const v = { charges: [charge(), due, grace] };
    expect(chargesFor(v, { discipline: "Kineticism" }).map((c) => c.key)).toEqual([KINETICISM]);
    expect(chargesFor(v, { discipline: "Necromancy: Path of the Graveborn" })).toEqual([]);
    expect(chargesFor(v, { discipline: "Necromancy: Path of the Graveborn", power: "Reaper's Due" })).toEqual([due]);
    expect(chargesFor(v, { other: "Obeah: Rayzeel's Grace" })).toEqual([grace]);
  });
});

describe("the tracker on the phone (issue #826)", () => {
  it("keeps charges within their most, as the server does, and names them", () => {
    const v = { ...view([charge({ value: 4 })]), expendables: [], derangements: { temporary: [] } } as unknown as PlayView;
    expect(applyChange(v, KINETICISM, 3)).toEqual([4, 5]);
    expect(applyChange(v, KINETICISM, -9)).toEqual([5, 0]);
    expect(trackerName(v, KINETICISM)).toBe("Kineticism charges");
  });

  it("counts a stack in a pool's line against the mark", () => {
    const trackers = trackersOf({ morality: null, beast: { value: 0 }, charges: [{ key: `${CHARGE}Reaper's Due`, value: 3 }] });
    expect(trackedValue({ label: "Reaper's Due", tracks: `${CHARGE}Reaper's Due` }, trackers)).toBe(3);
    expect(trackedValue({ label: "Reaper's Due", tracks: `${CHARGE}Other` }, trackers)).toBe(0);
  });
});
