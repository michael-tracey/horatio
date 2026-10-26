import { describe, expect, it } from "vitest";
import type { PlayView, PowerSwitch } from "../../api/types";
import { applySwitch, bloodMost, bloodPerTurn, boxes, describeSwitch, formsOn, healthMost, onKeys } from "./powers";
import { makeTap, withPending } from "./tracker";

const power = (over: Partial<PowerSwitch>): PowerSwitch => ({
  key: "fight form",
  name: "Shape of the Beast: fight form (wolf, Huge)",
  origin: "Protean 4",
  form: true,
  combines: [],
  page: "p. 155",
  changes: [],
  notes: [],
  health: [],
  attributes: [],
  focuses: [],
  blood_per_turn: 0,
  blood_half: false,
  on: false,
  ...over,
});

const fight = power({ health: [{ level: "Healthy", boxes: 2 }] });
const flight = power({ key: "flight form", name: "Shape of the Beast: flight form (bat)" });
const claws = power({ key: "Feral Claws", name: "Feral Claws", form: false });

function view(powers: PowerSwitch[], marks: string[] = []): PlayView {
  return {
    character_id: "c1",
    character_name: "Ursula",
    player_name: "Jane",
    kind: "pc",
    blood_name: "Blood",
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
    influence: [],
    powers: powers.map((p) => ({ ...p })),
    game: null,
    log: [],
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

  it("grows the Blood pool with Blood of Potency, and takes the extra away after", () => {
    const potency = power({ key: "Blood of Potency", name: "Blood of Potency", form: false, blood_half: true, blood_per_turn: 2 });
    const v = view([potency]);
    applySwitch(v, "Blood of Potency", 1);
    expect([bloodMost(v), v.blood.most, bloodPerTurn(v)]).toEqual([15, 15, 3]);
    v.blood.value = 14;
    applySwitch(v, "Blood of Potency", -1);
    expect([v.blood.value, v.blood.most, bloodPerTurn(v)]).toEqual([10, 10, 1]);
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
