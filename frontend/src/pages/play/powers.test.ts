import { describe, expect, it } from "vitest";
import type { PlayView, PowerSwitch } from "../../api/types";
import { addedNote, applyPick, applySwitch, bloodMost, bloodPerTurn, boxes, countedOptions, describePick, describeSwitch, formsOn, healthMost, onKeys, withPicks } from "./powers";
import { makeTap, tapToast, trackerName, withPending } from "./tracker";

const power = (over: Partial<PowerSwitch>): PowerSwitch => ({
  key: "fight form",
  name: "Shape of the Beast: fight form (wolf, Huge)",
  origin: "Protean 4",
  form: true,
  combines: [],
  page: "p. 155",
  changes: [],
  notes: [],
  added: [],
  health: [],
  attributes: [],
  focuses: [],
  blood_per_turn: 0,
  blood_half: false, blood_extra: 0,
  on: false,
  options: [],
  picked: [],
  qualities: [],
  fixed: [],
  turned_on: 0,
  kept: false,
  normal_form_only: false,
  counts_as_form: false,
  paused: false,
  ...over,
});

/** What a power picks each use: equipment qualities of a kind, or its own options (#821). */
const picks = (over: Partial<NonNullable<PowerSwitch["picks"]>>): NonNullable<PowerSwitch["picks"]> => ({
  kind: null,
  count: 1,
  kinds: [],
  only: [],
  immune: false,
  options: [],
  target: "self",
  ...over,
});

const fight = power({ health: [{ level: "Healthy", boxes: 2 }] });
const flight = power({ key: "flight form", name: "Shape of the Beast: flight form (bat)" });
const claws = power({ key: "Feral Claws", name: "Feral Claws", form: false });

function view(powers: PowerSwitch[], marks: string[] = [], forms = 1): PlayView {
  return {
    character_id: "c1",
    character_name: "Ursula",
    player_name: "Jane",
    kind: "pc",
    blood_name: "Blood",
    panels: { beast: true, frenzy: true, morality: true, generation: true, feed: true },
    splat: "vampire",
    tabs: ["sheet", "tracker", "pools", "status", "equipment"],
    clan: "Gangrel",
    sect: null,
    generation: 1,
    blood_per_turn: 1,
    herd: 0,
    blood: { value: 10, most: 10, start: 10 },
    retainers: [],
    blood_usual: 10,
    half_blood: false,
    willpower: { value: 6, most: 6, start: 6 },
    health: {
      levels: [
        { name: "Healthy", boxes: 3 },
        { name: "Injured", boxes: 3 },
        { name: "Incapacitated", boxes: 3 },
      ],
      marks,
      stamina_focus: false,
    },
    morality: null,
    beast: { value: 0, most: 5, start: 0 },
    derangements: { value: 0, most: 3, start: 0, least: 0, flaws: [], temporary: [] },
    expendables: [],
    equipment: [],
    equipped: [],
    influence: [],
    powers: powers.map((p) => ({ ...p })),
    forms,
    game: null,
    log: [],
    effects: [],
  };
}

describe("forms and powers", () => {
  it("adds a form's wound levels after the sheet's own, only while it is on", () => {
    expect(healthMost(view([fight]))).toBe(9);
    const on = view([{ ...fight, on: true }]);
    expect(healthMost(on)).toBe(11);
    expect(boxes(on).map((b) => `${b.level}${b.from ? " (form)" : ""}`)).toEqual([
      ...Array(3).fill("Healthy"),
      ...Array(2).fill("Healthy (form)"),
      ...Array(3).fill("Injured"),
      ...Array(3).fill("Incapacitated"),
    ]);
  });

  it("takes the damage in a form's levels away with them when it ends", () => {
    const v = view([{ ...fight, on: true }], ["normal", "normal", "normal", "aggravated", "normal", "normal"]);
    const said: string[] = [];
    expect(applySwitch(v, "fight form", -1, said)).toEqual([1, 0]);
    // The 4th and 5th marks were in the form's boxes; the 6th, in Injured, moves up.
    expect(v.health.marks).toEqual(["normal", "normal", "normal", "normal"]);
    expect(said).toEqual(["2 damage in its levels gone"]);
    expect(describeSwitch(v, "fight form", -1, said)).toBe("Out of Shape of the Beast: fight form (wolf, Huge): 2 damage in its levels gone");
  });

  it("keeps one form at a time, and powers go with it", () => {
    const v = view([fight, flight, claws]);
    applySwitch(v, "fight form", 1);
    applySwitch(v, "Feral Claws", 1);
    const said: string[] = [];
    applySwitch(v, "flight form", 1, said);
    expect(onKeys(v)).toEqual(["flight form", "Feral Claws"]);
    expect(formsOn(v).map((f) => f.key)).toEqual(["flight form"]);
    expect(said).toEqual(["out of Shape of the Beast: fight form (wolf, Huge)"]);
    expect(describeSwitch(v, "Feral Claws", 1)).toBe("Feral Claws on");
  });

  it("lets forms that combine be on together", () => {
    const mantle = power({ key: "Mantle of Atira", name: "Mantle of Atira", combines: ["Spiritwalker"] });
    const walker = power({ key: "Spiritwalker", name: "Spiritwalker", combines: ["Mantle of Atira"] });
    const v = view([mantle, walker, fight]);
    applySwitch(v, "Mantle of Atira", 1);
    applySwitch(v, "Spiritwalker", 1);
    expect(onKeys(v)).toEqual(["Mantle of Atira", "Spiritwalker"]);
    applySwitch(v, "fight form", 1);
    expect(onKeys(v)).toEqual(["fight form"]);
  });

  it("keeps two forms with Ravenous Conglomeration, never two of one power, and a third ends the first (#597)", () => {
    const horrid = power({ key: "Horrid Form", name: "Horrid Form", origin: "Vicissitude 4", health: [{ level: "Healthy", boxes: 1 }] });
    const blood = power({ key: "Blood Form", name: "Blood Form", origin: "Vicissitude 5" });
    const v = view([fight, flight, horrid, blood, claws], [], 2);
    applySwitch(v, "Horrid Form", 1);
    applySwitch(v, "fight form", 1);
    applySwitch(v, "Feral Claws", 1);
    // Both forms are on, and both forms' wound levels count.
    expect(formsOn(v).map((f) => f.key)).toEqual(["fight form", "Horrid Form"]);
    expect(healthMost(v)).toBe(12);

    // The bat is the same power as the wolf (Shape of the Beast), so it takes its place.
    const said: string[] = [];
    applySwitch(v, "flight form", 1, said);
    expect(onKeys(v)).toEqual(["flight form", "Horrid Form", "Feral Claws"]);
    expect(said).toEqual(["out of Shape of the Beast: fight form (wolf, Huge)"]);

    // A third form ends the one on longest: Horrid Form, not the bat that came after it.
    const third: string[] = [];
    applySwitch(v, "Blood Form", 1, third);
    expect(onKeys(v)).toEqual(["flight form", "Blood Form", "Feral Claws"]);
    expect(describeSwitch(v, "Blood Form", 1, third)).toBe("Turned into Blood Form: out of Horrid Form");
  });

  it("keeps the one-form rule without Ravenous Conglomeration, for forms of different powers too", () => {
    const horrid = power({ key: "Horrid Form", name: "Horrid Form", origin: "Vicissitude 4" });
    const v = view([fight, horrid]);
    applySwitch(v, "Horrid Form", 1);
    applySwitch(v, "fight form", 1);
    expect(formsOn(v).map((f) => f.key)).toEqual(["fight form"]);
  });

  it("knows the order the forms went on from the server, after a reload", () => {
    const horrid = power({ key: "Horrid Form", name: "Horrid Form", origin: "Vicissitude 4" });
    const blood = power({ key: "Blood Form", name: "Blood Form", origin: "Vicissitude 5" });
    // The fight form went on first, so it is the one a third form ends.
    const v = view([{ ...horrid, on: true, turned_on: 3 }, { ...fight, on: true, turned_on: 1 }, blood], [], 2);
    applySwitch(v, "Blood Form", 1);
    expect(formsOn(v).map((f) => f.key)).toEqual(["Horrid Form", "Blood Form"]);
  });

  it("grows the Blood pool with Blood of Potency, and takes the extra away after", () => {
    const potency = power({ key: "Blood of Potency", name: "Blood of Potency", form: false, blood_half: true, blood_per_turn: 2 });
    const v = view([potency]);
    applySwitch(v, "Blood of Potency", 1);
    expect([bloodMost(v), v.blood.most, bloodPerTurn(v)]).toEqual([15, 15, 3]);
    v.blood.value = 14;
    applySwitch(v, "Blood of Potency", -1);
    expect([v.blood.value, v.blood.most, bloodPerTurn(v)]).toEqual([10, 10, 1]);
  });

  it("names the power and page a note added to a switch comes from (#601)", () => {
    expect(addedNote({ source: "Momentum Swing", page: "Vol. 2, p. 200", note: "Deflect a projectile." })).toBe("Momentum Swing (Vol. 2, p. 200): Deflect a projectile.");
  });

  it("shows a switch tap at once, before the server has it, and Undo takes it back", () => {
    const tap = makeTap({ kind: "change", tracker: "power:fight form", amount: 1 }, "g1");
    const shown = withPending(view([fight, flight]), [tap]);
    expect(onKeys(shown)).toEqual(["fight form"]);
    expect(healthMost(shown)).toBe(11);
    expect(shown.log[0]!.text).toBe("Turned into Shape of the Beast: fight form (wolf, Huge)");
    const undone = withPending(view([fight, flight]), [tap, makeTap({ kind: "undo", undoes: tap.id }, "g1")]);
    expect(onKeys(undone)).toEqual([]);
  });
});

describe("qualities picked each use (#599)", () => {
  const option = (name: string) => ({ name, play: "", page: null, modifiers: [] });
  const marble = power({
    key: "Flesh of Marble",
    name: "Protean: Flesh of Marble",
    form: false,
    picks: picks({ kind: "protective", count: 2 }),
    options: ["Ballistic", "Hardened", "Rugged"].map(option),
  });

  it("picks while it is on, dropping the oldest past its count", () => {
    const v = view([marble]);
    expect(applyPick(v, "Flesh of Marble/Ballistic", 1)).toEqual([0, 0]);
    applySwitch(v, "Flesh of Marble", 1);
    expect(applyPick(v, "Flesh of Marble/Ballistic", 1)).toEqual([0, 1]);
    applyPick(v, "Flesh of Marble/Hardened", 1);
    const said: string[] = [];
    applyPick(v, "Flesh of Marble/Rugged", 1, said);
    expect(v.powers[0]!.picked).toEqual(["Hardened", "Rugged"]);
    expect(said).toEqual(["dropped Ballistic (2 at most)"]);
    expect(describePick(v, "Flesh of Marble/Rugged", 1, said)).toBe("Picked Rugged for Protean: Flesh of Marble: dropped Ballistic (2 at most)");
    expect(withPicks(v.powers[0]!)).toBe("Protean: Flesh of Marble (Hardened, Rugged)");
    expect(applyPick(v, "Flesh of Marble/Hardened", -1)).toEqual([1, 0]);
    expect(describePick(v, "Flesh of Marble/Hardened", -1)).toBe("Dropped Hardened from Protean: Flesh of Marble");
    // Not one of its kind's.
    expect(applyPick(v, "Flesh of Marble/Accurate", 1)).toBeNull();
  });

  it("drops them all when it is switched off", () => {
    const v = view([{ ...marble, on: true, picked: ["Ballistic", "Rugged"] }]);
    applySwitch(v, "Flesh of Marble", -1);
    applySwitch(v, "Flesh of Marble", 1);
    expect(v.powers[0]!.picked).toEqual([]);
    expect(withPicks(v.powers[0]!)).toBe("Protean: Flesh of Marble");
  });

  it("shows a pick at once, with its toast, and Undo takes it back", () => {
    const v = view([{ ...marble, on: true, picked: ["Ballistic", "Hardened"] }]);
    const tap = makeTap({ kind: "change", tracker: "pick:Flesh of Marble/Rugged", amount: 1 }, "g1");
    expect(tapToast(withPending(v, []), tap)).toBe("Picked Rugged for Protean: Flesh of Marble: dropped Ballistic (2 at most)");
    expect(trackerName(v, "pick:Flesh of Marble/Rugged")).toBe("Protean: Flesh of Marble: Rugged");
    const shown = withPending(v, [tap]);
    expect(shown.powers[0]!.picked).toEqual(["Hardened", "Rugged"]);
    expect(v.powers[0]!.picked).toEqual(["Ballistic", "Hardened"]);
    const undone = withPending(v, [tap, makeTap({ kind: "undo", undoes: tap.id }, "g1")]);
    expect(undone.powers[0]!.picked).toEqual(["Ballistic", "Hardened"]);
  });
});

describe("a power kept until undone (#822)", () => {
  const visage = power({ key: "Alien beauty", name: "Malleable Visage: alien beauty", form: false, kept: true, normal_form_only: true, health: [{ level: "Healthy", boxes: 1 }], blood_per_turn: 1 });
  const heart = power({ key: "Heart removed", name: "Heart of Darkness: heart removed", form: false, kept: true });

  it("is paused while a form is on when it changes the normal form only, and counts again after", () => {
    const v = view([{ ...visage, on: true }, { ...heart, on: true }, fight]);
    expect(onKeys(v)).toEqual(["Alien beauty", "Heart removed"]);
    expect(healthMost(v)).toBe(10);
    expect(bloodPerTurn(v)).toBe(2);
    applySwitch(v, "fight form", 1);
    // In the form: the visage's level and Blood go, the form's come; the heart stays out.
    expect(onKeys(v)).toEqual(["Heart removed", "fight form"]);
    expect(healthMost(v)).toBe(11);
    expect(bloodPerTurn(v)).toBe(1);
    applySwitch(v, "fight form", -1);
    expect(onKeys(v)).toEqual(["Alien beauty", "Heart removed"]);
  });

  it("used again while on, replaces the one on and stays on", () => {
    const v = view([{ ...heart, on: true, turned_on: 1 }]);
    const said: string[] = [];
    expect(applySwitch(v, "Heart removed", 1, said)).toEqual([1, 1]);
    expect(said).toEqual(["replaces the one on before"]);
    expect(describeSwitch(v, "Heart removed", 1, said)).toBe("Heart of Darkness: heart removed on: replaces the one on before");
    expect(applySwitch(v, "Heart removed", -1)).toEqual([1, 0]);
  });
});

describe("a power's own options picked each use (#821)", () => {
  type Option = NonNullable<PowerSwitch["picks"]>["options"][number];
  const own = (name: string, over: Partial<Option> = {}): Option => ({
    name,
    key: `Mythic Form/${name}`,
    page: "Vol. 2, p. 234",
    note: "",
    health: [],
    attributes: [],
    focuses: [],
    blood_per_turn: 0,
    blood_half: false, blood_extra: 0,
    qualities: [],
    normal_form_only: null,
    ...over,
  });
  const chip = (name: string) => ({ name, play: "", page: "Vol. 2, p. 234", modifiers: [] });
  const mythic = power({
    key: "Mythic Form",
    name: "Protean: Mythic Form",
    form: false,
    picks: picks({ count: 2, options: [own("Tough", { health: [{ level: "Healthy", boxes: 4 }] }), own("Agile"), own("Vicious")] }),
    options: ["Tough", "Agile", "Vicious"].map(chip),
  });

  it("counts an option picked as a switch on, with its levels after the power's", () => {
    const v = view([mythic]);
    applySwitch(v, "Mythic Form", 1);
    expect(onKeys(v)).toEqual(["Mythic Form"]);
    applyPick(v, "Mythic Form/Tough", 1);
    applyPick(v, "Mythic Form/Agile", 1);
    expect(onKeys(v)).toEqual(["Mythic Form", "Mythic Form/Tough", "Mythic Form/Agile"]);
    expect(countedOptions(v).map((o) => o.name)).toEqual(["Tough", "Agile"]);
    const tough = boxes(v).filter((b) => b.option === "Tough");
    expect(tough).toHaveLength(4);
    expect(tough.every((b) => b.from?.key === "Mythic Form")).toBe(true);
  });

  it("takes the damage in a dropped option's levels with them, as the server does", () => {
    const v = view([mythic]);
    applySwitch(v, "Mythic Form", 1);
    applyPick(v, "Mythic Form/Tough", 1);
    const before = healthMost(v);
    v.health.marks = Array(before).fill("normal");
    applyPick(v, "Mythic Form/Agile", 1);
    const said: string[] = [];
    applyPick(v, "Mythic Form/Vicious", 1, said);
    expect(v.powers[0]!.picked).toEqual(["Agile", "Vicious"]);
    expect(said).toEqual(["dropped Tough (2 at most)", "4 damage in its levels gone"]);
    expect(healthMost(v)).toBe(before - 4);
    expect(v.health.marks).toHaveLength(before - 4);
  });

  it("pauses an option of a power that changes the normal form only while a form is on", () => {
    const visage = power({
      key: "Visage",
      name: "Malleable Visage",
      form: false,
      on: true,
      kept: true,
      normal_form_only: true,
      picks: picks({ options: [own("Beauty", { key: "Visage/Beauty", blood_per_turn: 1 }), own("Stomach", { key: "Visage/Stomach", normal_form_only: false, blood_half: true })] }),
      picked: ["Beauty"],
      options: ["Beauty", "Stomach"].map(chip),
    });
    const beast = { ...fight, on: true };
    expect(onKeys(view([visage]))).toEqual(["Visage", "Visage/Beauty"]);
    expect(bloodPerTurn(view([visage]))).toBe(1 + view([]).blood_per_turn);
    // A form pauses the power and the option it doesn't keep in forms.
    expect(onKeys(view([visage, beast]))).toEqual(["fight form"]);
    const stomach = { ...visage, picked: ["Stomach"] };
    expect(onKeys(view([stomach, beast]))).toEqual(["fight form", "Visage/Stomach"]);
    expect(bloodMost(view([stomach, beast]))).toBe(view([]).blood_usual + Math.ceil(view([]).blood_usual / 2));
  });

  it("picks again when a kept power is used again", () => {
    const visage = power({ key: "Visage", name: "Malleable Visage", form: false, on: true, kept: true, picks: picks({ options: [own("Beauty", { key: "Visage/Beauty" })] }), picked: ["Beauty"], options: [chip("Beauty")] });
    const v = view([visage]);
    const said: string[] = [];
    applySwitch(v, "Visage", 1, said);
    expect(said).toEqual(["replaces the one on before"]);
    expect(v.powers[0]!.picked).toEqual([]);
  });
});

describe("health levels given up and amounts chosen each use (#824)", () => {
  type Option = NonNullable<PowerSwitch["picks"]>["options"][number];
  const own = (name: string, over: Partial<Option> = {}): Option => ({
    name,
    key: `Bonecraft/${name}`,
    page: "p. 168",
    note: "",
    health: [],
    attributes: [],
    focuses: [],
    blood_per_turn: 0,
    blood_half: false,
    blood_extra: 0,
    qualities: [],
    normal_form_only: null,
    ...over,
  });
  const chip = (name: string) => ({ name, play: "", page: "p. 168", modifiers: [] });
  const toughs = [1, 2, 3].map((n) => own(`Tough: ${n}`, { base: "Tough", amount: n, amount_label: "Physical given up", health: [{ level: "Healthy", boxes: n }], attributes: [{ attribute: "Physical", amount: -n }] }));
  const limbs = own("Extra Limbs", { health: [{ level: "Healthy", boxes: -2 }] });
  const stomach = own("Second Stomach: 3", { base: "Second Stomach", amount: 3, health: [{ level: "Healthy", boxes: -3 }], blood_extra: 6 });
  const bonecraft = power({
    key: "Bonecraft",
    name: "Vicissitude: Bonecraft",
    form: false,
    picks: picks({ count: 2, options: [...toughs, limbs, stomach] }),
    options: [...toughs, limbs, stomach].map((o) => chip(o.name)),
  });

  it("takes the levels given up off the sheet's own, and gives them back when the power ends", () => {
    const v = view([bonecraft]);
    const before = healthMost(v);
    const healthy = boxes(v).filter((b) => b.level === "Healthy").length;
    applySwitch(v, "Bonecraft", 1);
    applyPick(v, "Bonecraft/Extra Limbs", 1);
    expect(healthMost(v)).toBe(before - 2);
    expect(boxes(v).filter((b) => b.level === "Healthy" && b.from === null)).toHaveLength(healthy - 2);
    v.health.marks = ["normal", "normal"];
    applySwitch(v, "Bonecraft", -1);
    expect(healthMost(v)).toBe(before);
    // Damage marked stays: the levels come back, the damage with them.
    expect(v.health.marks).toEqual(["normal", "normal"]);
  });

  it("never gives up more than a category has, and adds the Blood an option gives", () => {
    const v = view([bonecraft]);
    const healthy = boxes(v).filter((b) => b.level === "Healthy").length;
    applySwitch(v, "Bonecraft", 1);
    applyPick(v, "Bonecraft/Second Stomach: 3", 1);
    expect(boxes(v).filter((b) => b.level === "Healthy")).toHaveLength(Math.max(0, healthy - 3));
    expect(bloodMost(v)).toBe(v.blood_usual + 6);
  });

  it("picks one amount of an option at a time, as the server does", () => {
    const v = view([bonecraft]);
    applySwitch(v, "Bonecraft", 1);
    applyPick(v, "Bonecraft/Tough: 1", 1);
    const said: string[] = [];
    expect(applyPick(v, "Bonecraft/Tough: 3", 1, said)).toEqual([0, 1]);
    expect(v.powers[0]!.picked).toEqual(["Tough: 3"]);
    expect(said).toEqual(["in place of Tough: 1"]);
    expect(boxes(v).filter((b) => b.option === "Tough: 3")).toHaveLength(3);
    expect(withPicks(v.powers[0]!)).toBe("Vicissitude: Bonecraft (Tough: 3)");
  });
});
