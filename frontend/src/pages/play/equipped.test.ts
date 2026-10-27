import { describe, expect, it } from "vitest";
import type { EquipmentModifier, PlayItem, PlayView, TestPool } from "../../api/types";
import { applyEquip, describeEquip, equipmentModifiers } from "./equipped";
import { breakdown, describe as describeModifier, situations, total } from "./pools";

const mod = (over: Partial<EquipmentModifier>): EquipmentModifier => ({ quality: "Accurate", label: "Katana: Accurate", amount: 2, pools: "pool:attack:Melee", when: "attacks with it", situational: false, ...over });
const item = (id: string, kind: string, hands: number | null = null, modifiers: EquipmentModifier[] = []): PlayItem => ({ id, name: id, kind, hands, modifiers });

const katana = item("Katana", "melee", 2, [mod({})]);
const pistol = item("Pistol", "ranged", 1, [mod({ quality: "Fast", label: "Pistol: Fast", amount: 3, pools: "pool:initiative", when: "fighting with it" })]);
const knife = item("Knife", "melee", 1, [mod({ quality: "Fast", label: "Knife: Fast", amount: 3, pools: "pool:initiative", when: "fighting with it" })]);
const dagger = item("Dagger", "melee", 1);
const vest = item("Flak Vest", "protective", null, [
  mod({ quality: "Ballistic", label: "Flak Vest: Ballistic", amount: 3, pools: "pool:dodge", when: "against firearms", situational: true }),
  mod({ quality: "Ballistic", label: "Flak Vest: Ballistic", amount: 1, pools: "pool:dodge", when: "against Brawl, Melee and thrown weapons", situational: true }),
]);
const mail = item("Chain Mail", "protective");
const laptop = item("Laptop", "miscellaneous");
const picks = item("Lock-picks", "miscellaneous");

function view(equipped: string[] = []): Pick<PlayView, "equipment" | "equipped"> {
  return { equipment: [katana, pistol, knife, dagger, vest, mail, laptop, picks], equipped };
}

describe("equipping", () => {
  it("equips and takes off, saying before and after", () => {
    const v = view();
    expect(applyEquip(v, "Pistol", 1)).toEqual([0, 1]);
    expect(applyEquip(v, "Pistol", 1)).toEqual([1, 1]);
    expect(applyEquip(v, "Pistol", -1)).toEqual([1, 0]);
    expect(v.equipped).toEqual([]);
    expect(applyEquip(v, "Sword of Saulot", 1)).toBeNull();
  });

  it("holds two hands' worth of weapons, putting away the one equipped longest", () => {
    const v = view(["Pistol", "Knife"]);
    const said: string[] = [];
    applyEquip(v, "Dagger", 1, said);
    expect(v.equipped).toEqual(["Knife", "Dagger"]);
    expect(said).toEqual(["put away Pistol (two hands at most)"]);
    applyEquip(v, "Katana", 1, said);
    expect(v.equipped).toEqual(["Katana"]);
    expect(describeEquip(v, "Katana", 1, said.slice(1))).toBe("Equipped Katana: put away Knife (two hands at most), put away Dagger (two hands at most)");
  });

  it("wears one piece of protective gear, and counts one piece of miscellaneous gear, at a time", () => {
    const v = view(["Flak Vest", "Laptop", "Pistol"]);
    const said: string[] = [];
    applyEquip(v, "Chain Mail", 1, said);
    applyEquip(v, "Lock-picks", 1, said);
    expect(v.equipped).toEqual(["Pistol", "Chain Mail", "Lock-picks"]);
    expect(said).toEqual(["took off Flak Vest (one worn at a time)", "put away Laptop (one piece's bonus at a time)"]);
    expect(describeEquip(v, "Pistol", -1)).toBe("Unequipped Pistol");
  });
});

const dodge: TestPool = {
  key: "dodge",
  name: "Dodge",
  group: "Combat",
  parts: [
    { label: "Physical", value: 5 },
    { label: "Dodge", value: 2 },
  ],
  total: 7,
  versus: null,
  adds_willpower: false,
  willpower_floor: 0,
  variants: [],
  notes: [],
  switched: [],
};
const melee: TestPool = { ...dodge, key: "attack:Melee", name: "Melee attack", parts: [{ label: "Physical", value: 5 }, { label: "Melee", value: 3 }], total: 8 };
const initiative: TestPool = { ...dodge, key: "initiative", name: "Initiative", parts: [{ label: "Physical", value: 5 }], total: 5 };

describe("equipment modifiers", () => {
  it("are the equipped items' own, on", () => {
    const found = equipmentModifiers([katana, vest], ["Katana"]);
    expect(found).toEqual([{ id: "Katana/0", label: "Katana: Accurate", amount: 2, pools: "pool:attack:Melee", when: "attacks with it", on: true, situational: false }]);
    expect(total(melee, 0, found)).toBe(10);
    expect(breakdown(melee, 0, found)).toBe("Physical 5 + Melee 3 + Katana: Accurate 2");
    expect(equipmentModifiers([katana], [])).toEqual([]);
  });

  it("count a bonus that holds only sometimes apart from the total", () => {
    const found = equipmentModifiers([vest], ["Flak Vest"]);
    expect(total(dodge, 0, found)).toBe(7);
    expect(situations(dodge, found)).toEqual([
      { when: "against firearms", parts: [{ label: "Flak Vest: Ballistic", value: 3 }] },
      { when: "against Brawl, Melee and thrown weapons", parts: [{ label: "Flak Vest: Ballistic", value: 1 }] },
    ]);
    expect(situations(melee, found)).toEqual([]);
    expect(describeModifier(found[0]!, [dodge])).toBe("+3 Dodge, against firearms");
  });

  it("count the same bonus from a second weapon once", () => {
    const found = equipmentModifiers([pistol, knife], ["Pistol", "Knife"]);
    expect(found.map((m) => m.id)).toEqual(["Pistol/0"]);
    expect(total(initiative, 0, found)).toBe(8);
  });

  it("say what a piece of miscellaneous gear's bonus is for", () => {
    expect(describeModifier({ amount: 1, pools: "purpose", when: "for its purpose, with the skill" }, [])).toBe("+1 for its purpose, with the skill");
  });
});
