import { describe, expect, it } from "vitest";
import type { BondOut } from "./api/types";
import { groupBonds, levelName, levelText, partyIn, statusText } from "./bonds";

const bond = (id: string, thrall: string, regnant: string, status = "active", level = 1): BondOut => ({
  id,
  thrall: { character_id: thrall === "Lady Ophelia" ? null : `c-${thrall}`, name: thrall, kind: thrall === "Lady Ophelia" ? null : "pc" },
  regnant: { character_id: `c-${regnant}`, name: regnant, kind: "pc" },
  level,
  status,
  known_to_regnant: false,
  ended_at: null,
  ended_reason: "",
  last_drink: null,
  entries: [],
});

describe("blood bonds", () => {
  it("says each level as the thrall feels it, with what it does", () => {
    expect(levelText(1).line).toBe("First drink: you're drawn to them");
    expect(levelText(2)).toEqual({
      line: "Second drink: you can't easily turn against them",
      effect: "−1 to Social defence against their powers. Harming them costs 1 Willpower an hour.",
    });
    expect(levelText(3).line).toBe("Full bond: they come before everyone else");
    expect(levelName(3)).toBe("Full bond");
  });

  it("says what became of a bond", () => {
    expect(statusText({ status: "active", ended_reason: "" })).toBe("Active");
    expect(statusText({ status: "broken", ended_reason: "True love" })).toBe("Broken: True love");
    expect(statusText({ status: "ended", ended_reason: "Wiped away by the full bond to Bram." })).toBe("Ended: Wiped away by the full bond to Bram.");
  });

  it("groups bonds by thrall or regnant, open ones first", () => {
    const bonds = [bond("1", "Cora", "Bram"), bond("2", "Agnes", "Vidal", "ended"), bond("3", "Agnes", "Bram", "active", 3), bond("4", "Lady Ophelia", "Bram")];
    expect(groupBonds(bonds, "thrall").map((g) => [g.name, g.bonds.map((b) => b.id)])).toEqual([
      ["Agnes", ["3", "2"]],
      ["Cora", ["1"]],
      ["Lady Ophelia", ["4"]],
    ]);
    expect(groupBonds(bonds, "regnant").map((g) => [g.name, g.bonds.map((b) => b.id)])).toEqual([
      ["Bram", ["3", "1", "4"]],
      ["Vidal", ["2"]],
    ]);
  });

  it("names a side as the API takes it", () => {
    expect(partyIn("c:123", "")).toEqual({ character_id: "123", name: "" });
    expect(partyIn("name", " Lady Ophelia ")).toEqual({ name: "Lady Ophelia" });
    expect(partyIn("name", " ")).toBeNull();
    expect(partyIn("", "")).toBeNull();
  });
});
