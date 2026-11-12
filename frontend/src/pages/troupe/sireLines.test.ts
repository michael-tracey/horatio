import { describe, expect, it } from "vitest";
import type { SireLineNodeOut } from "../../api/types";
import { about, loneCount, ordinal, sireRows, sireTree, type SireTree } from "./sireLines";

const node = (key: string, sire: string | null = null, extra: Partial<SireLineNodeOut> = {}): SireLineNodeOut => ({
  key,
  character_id: key,
  name: key,
  clan: "Ventrue",
  generation: null,
  left_reason: null,
  retired: false,
  kind: "pc",
  sire_key: sire,
  ...extra,
});

const names = (t: SireTree): unknown => (t.node ? { [t.node.name]: t.children.map(names) } : t.children.map(names));

describe("sire lines", () => {
  const nodes = [node("Elsa"), node("Berit", "Elsa"), node("Anna", "Elsa"), node("Carl", "Anna"), node("Lone")];

  it("hangs childer from their sire, by name, under one hidden root", () => {
    expect(names(sireTree(nodes))).toEqual([{ Elsa: [{ Anna: [{ Carl: [] }] }, { Berit: [] }] }]);
  });

  it("leaves out those with no line unless asked, and counts them", () => {
    expect(loneCount(nodes)).toBe(1);
    expect(names(sireTree(nodes, { lone: true }))).toEqual([{ Elsa: [{ Anna: [{ Carl: [] }] }, { Berit: [] }] }, { Lone: [] }]);
  });

  it("folds a branch and says how many are under it", () => {
    const folded = sireTree(nodes, { collapsed: new Set(["Elsa"]) });
    expect(folded.children[0]!.children).toEqual([]);
    expect(folded.children[0]!.folded).toBe(3);
  });

  it("makes a root of one whose sire isn't there", () => {
    expect(names(sireTree([node("Anna", "Gone"), node("Carl", "Anna")]))).toEqual([{ Anna: [{ Carl: [] }] }]);
  });

  it("says what each is under its name, and lists them as a table", () => {
    expect(about(node("Gone", null, { retired: true, left_reason: "final_death", generation: 9 }))).toEqual(["Ventrue", "9th generation", "Final Death"]);
    expect(about(node("named:x", null, { kind: "named", clan: null, character_id: null }))).toEqual(["known by name only"]);
    expect(sireRows([node("Anna", "Elsa"), node("Elsa")])).toEqual([
      { name: "Anna", sire: "Elsa", about: "Ventrue" },
      { name: "Elsa", sire: "—", about: "Ventrue" },
    ]);
    expect([1, 2, 3, 4, 11, 12, 13, 21].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st"]);
  });
});
