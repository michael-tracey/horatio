import { describe, expect, it } from "vitest";
import type { EquipmentOut, EquipmentQualityOut } from "../../api/types";
import { NEW_ITEM, body, combatFirst, factsText, fromTemplate, givenText, gradesOf, kindText, playText, qualityChoices, qualityText } from "./equipment";

function quality(kind: string, name: string, more: Partial<EquipmentQualityOut> = {}): EquipmentQualityOut {
  return {
    kind,
    name,
    effect: "",
    play: "",
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
    expect(fromTemplate({ name: "Silver Dagger", kind: "melee", grade: "standard", qualities: [{ name: "Concealable", detail: "" }, { name: "Silver", detail: "" }], page: "521", facts: {} as never, archaic: false, description: "" })).toEqual({
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
      archaic: false,
      effects: [{ name: "Glows", effect: "Sheds light." }],
      description: "Old.",
    });
    expect([own.grade, own.crafted, own.effects, own.description]).toEqual(["special", true, [{ name: "Glows", effect: "Sheds light." }], "Old."]);
  });

  it("marks the book's Bow archaic, and sends archaic only for a ranged weapon", () => {
    const bow = fromTemplate({ name: "Bow", kind: "ranged", grade: "standard", qualities: [], page: "524", facts: {} as never, archaic: true, description: "" });
    expect(bow.archaic).toBe(true);
    expect(body(bow).archaic).toBe(true);
    expect(body({ ...bow, kind: "melee" }).archaic).toBe(false);
    expect(kindText(RULES, { kind: "ranged", kind_name: "Ranged weapon", grade: "standard", crafted: false, archaic: true })).toBe("Archaic ranged weapon");
  });

  it("starts a Vampiric Text from the book's, with its line, and sends no qualities, crafting or cheap grade for one", () => {
    const nod = fromTemplate({ name: "The Book of Nod", kind: "text", grade: "standard", qualities: [], page: "28, 421 & 453", facts: {} as never, archaic: false, description: "The legends of Caine." });
    expect([nod.kind, nod.description]).toEqual(["text", "The legends of Caine."]);
    const sent = body({ ...nod, grade: "cheap", crafted: true, qualities: [{ name: "Accurate", detail: "" }] });
    expect([sent.grade, sent.crafted, sent.qualities]).toEqual(["standard", false, []]);
    expect(gradesOf("text").map(([g]) => g)).toEqual(["standard", "special"]);
    expect(gradesOf("melee").map(([g]) => g)).toEqual(["cheap", "standard", "special"]);
  });

  it("says where an item came from: given by a troupe, or moved from the sheet", () => {
    expect(givenText({ from_sheet: false, given_by_name: "Lead", troupe_name: "Lords of the Night" })).toBe("Given by Lead of Lords of the Night");
    expect(givenText({ from_sheet: true, given_by_name: null, troupe_name: null })).toBe("Moved from the sheet, where it was a trait");
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
    expect(kindText(undefined, { kind: "ranged", kind_name: "Ranged weapon", grade: "cheap", crafted: false })).toBe("Cheap ranged weapon");
  });

  it("puts weapons first, then armour, then the rest, keeping each kind's order", () => {
    const items = [
      { name: "Laptop", kind: "miscellaneous" },
      { name: "Vest", kind: "protective" },
      { name: "Rifle", kind: "ranged" },
      { name: "Dagger", kind: "melee" },
      { name: "Axe", kind: "melee" },
    ];
    expect(combatFirst(items).map((i) => i.name)).toEqual(["Dagger", "Axe", "Rifle", "Vest", "Laptop"]);
  });

  it("says what a quality does at the table", () => {
    const fast = { name: "Fast", detail: "", effect: "+3 initiative when fighting with it.", play: "+3 initiative", page: "517" };
    expect(playText(fast)).toBe("Fast: +3 initiative");
    expect(playText({ ...fast, name: "Customized", detail: "hacking", play: "+2 in its circumstance" })).toBe("Customized (hacking): +2 in its circumstance");
    expect(playText({ ...fast, play: null })).toBe("Fast: +3 initiative when fighting with it.");
    expect(playText({ ...fast, play: null, effect: null })).toBe("Fast");
  });
});
