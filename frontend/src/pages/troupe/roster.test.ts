import { describe, expect, it } from "vitest";
import { ageRank, clanText, nextSort, showOf, shows, sortRows } from "./roster";

describe("clanText", () => {
  it("names the clan, or says a vampire has none yet", () => {
    expect(clanText("Brujah", "Neonate")).toBe("Brujah");
    expect(clanText(null, "Elder")).toBe("No clan yet");
  });

  it("says nothing for what is no vampire: its age says what it is", () => {
    expect(clanText(null, "Mortal")).toBeNull();
    expect(clanText(null, "Werewolf")).toBeNull();
    expect(clanText(null, "Ghoul")).toBeNull();
    // A ghoul's clan is its domitor's.
    expect(clanText("Nosferatu", "Ghoul")).toBe("Nosferatu");
  });
});

describe("sorting", () => {
  const rows = [
    { name: "Mara", age: "Elder", player: "Jo" },
    { name: "agnes", age: "Neonate", player: null },
    { name: "Nell", age: "Mortal", player: "Al" },
    { name: "Bram", age: "Ancilla", player: "Al" },
  ];
  const names = (list: typeof rows) => list.map((r) => r.name);

  it("goes A to Z, Z to A, then back to the list's own order", () => {
    expect(nextSort(null, "character")).toEqual({ by: "character", descending: false });
    expect(nextSort({ by: "character", descending: false }, "character")).toEqual({ by: "character", descending: true });
    expect(nextSort({ by: "character", descending: true }, "character")).toBeNull();
    expect(nextSort({ by: "character", descending: true }, "age")).toEqual({ by: "age", descending: false });
  });

  it("sorts names regardless of case, and keeps the list's order among equals", () => {
    expect(names(sortRows(rows, (r) => r.name, false))).toEqual(["agnes", "Bram", "Mara", "Nell"]);
    expect(names(sortRows(rows, (r) => r.player, false))).toEqual(["Nell", "Bram", "Mara", "agnes"]);
    expect(names(sortRows(rows, null, false))).toEqual(["Mara", "agnes", "Nell", "Bram"]);
  });

  it("puts a row with nothing to sort by last, either way", () => {
    expect(names(sortRows(rows, (r) => r.player, true))).toEqual(["Mara", "Nell", "Bram", "agnes"]);
  });

  it("sorts ages youngest first, with what is no vampire after the elders", () => {
    expect(names(sortRows(rows, (r) => ageRank(r.age), false))).toEqual(["agnes", "Bram", "Mara", "Nell"]);
    expect(names(sortRows(rows, (r) => ageRank(r.age), true))).toEqual(["Nell", "Mara", "Bram", "agnes"]);
  });

  it("sorts numbers as numbers", () => {
    const values = [{ v: 10 }, { v: 2 }, { v: 0 }];
    expect(sortRows(values, (r) => r.v, false).map((r) => r.v)).toEqual([0, 2, 10]);
  });
});

describe("showing player characters, NPCs or everyone", () => {
  it("opens on player characters, whatever else the address holds", () => {
    expect(showOf(null)).toBe("pcs");
    expect(showOf("npcs")).toBe("npcs");
    expect(showOf("everyone")).toBe("everyone");
    expect(showOf("ghosts")).toBe("pcs");
  });

  it("shows each kind of character where it belongs", () => {
    expect([shows("pcs", "pc"), shows("pcs", "npc")]).toEqual([true, false]);
    expect([shows("npcs", "pc"), shows("npcs", "npc")]).toEqual([false, true]);
    expect([shows("everyone", "pc"), shows("everyone", "npc")]).toEqual([true, true]);
  });
});
