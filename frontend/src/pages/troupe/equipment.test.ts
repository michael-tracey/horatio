import { describe, expect, it } from "vitest";
import type { EquipmentOut, EquipmentQualityOut } from "../../api/types";
import { NEW_ITEM, body, factsText, fromTemplate, kindText, qualityChoices, qualityText } from "./equipment";

function quality(kind: string, name: string, more: Partial<EquipmentQualityOut> = {}): EquipmentQualityOut {
  return {
    kind,
    name,
    effect: "",
    page: null,
    two_handed: false,
    needs_one_hand: false,
    no_slot_when_crafted: false,
    repeatable: false,
    needs_detail: false,
    detail_prompt: null,
    ammo: false,
    excludes: [],
    ...more,
  };
}

const RULES = {
  kinds: [{ key: "melee", name: "Melee weapon", description: "", hands: 1, damage: 1, shots: null, range: "2 steps", note: "", page: "516" }],
  grades: [],
  qualities: [quality("melee", "Silver"), quality("melee", "Accurate"), quality("ranged", "Accurate"), quality("miscellaneous", "Superior", { repeatable: true })],
  templates: [],
} as EquipmentOut;

describe("equipment", () => {
  it("offers a kind's qualities not yet chosen, and a repeatable one again", () => {
    expect(qualityChoices(RULES, "melee", [{ name: "Silver", detail: "" }]).map((q) => q.name)).toEqual(["Accurate"]);
    expect(qualityChoices(RULES, "miscellaneous", [{ name: "Superior", detail: "" }]).map((q) => q.name)).toEqual(["Superior"]);
  });

  it("starts from a template, the book's or the troupe's", () => {
    expect(fromTemplate({ name: "Silver Dagger", kind: "melee", grade: "standard", qualities: [{ name: "Concealable", detail: "" }, { name: "Silver", detail: "" }], page: "521", facts: {} as never })).toEqual({
      ...NEW_ITEM,
      name: "Silver Dagger",
      qualities: [
        { name: "Concealable", detail: "" },
        { name: "Silver", detail: "" },
      ],
    });
    const own = fromTemplate({
      id: "t",
      name: "Relic",
      kind: "melee",
      grade: "special",
      qualities: [],
      crafted: true,
      effects: [{ name: "Glows", effect: "Sheds light." }],
      description: "Old.",
    });
    expect([own.grade, own.crafted, own.effects, own.description]).toEqual(["special", true, [{ name: "Glows", effect: "Sheds light." }], "Old."]);
  });

  it("sends a special item's effects only", () => {
    const draft = { ...NEW_ITEM, name: "Knife", effects: [{ name: "Glows", effect: "Sheds light." }] };
    expect(body(draft).effects).toEqual([]);
    expect(body({ ...draft, grade: "special" }).effects).toEqual(draft.effects);
  });

  it("says what an item is in a line", () => {
    expect(factsText({ hands: 2, damage: 2, shots: 12, range: "half a mile", aggravated_against: [] })).toBe("2 hands · 2 damage · 12 shots · range half a mile");
    expect(factsText({ hands: 1, damage: 1, shots: null, range: "2 steps", aggravated_against: [] })).toBe("1 hand · 1 damage · range 2 steps");
    expect(factsText({ hands: null, damage: null, shots: null, range: null, aggravated_against: [] })).toBe("");
    expect(qualityText({ name: "Customized", detail: "hacking" })).toBe("Customized: hacking");
    expect(kindText(RULES, { kind: "melee", grade: "special", crafted: false })).toBe("Special melee weapon");
    expect(kindText(RULES, { kind: "melee", grade: "standard", crafted: true })).toBe("Crafted melee weapon");
  });
});
