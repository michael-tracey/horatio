import { describe, expect, it } from "vitest";
import { allowanceWarning, another, cycleDate, findCharacters, specializationGroups, type EntryFields } from "./logInfluence";

const character = (name: string, kind = "pc") => ({ id: name, name, kind, in_troupe: true });

describe("the Log influence tool", () => {
  it("finds characters by any part of their name, those starting with it first", () => {
    const all = [character("Lady Agnes"), character("Agnes"), character("Prince Vasquez", "npc")];
    expect(findCharacters(all, "agn").map((c) => c.name)).toEqual(["Agnes", "Lady Agnes"]);
    expect(findCharacters(all, " ")).toHaveLength(3);
  });

  it("offers the character's own specialisations first, then every other", () => {
    expect(specializationGroups(["Police"], ["Finance", "Police", "Church"])).toEqual({ own: ["Police"], others: ["Church", "Finance"] });
    // One already on an entry stays offered.
    expect(specializationGroups([], ["Finance"], "Old Money").others).toEqual(["Finance", "Old Money"]);
  });

  it("dates by a cycle when it opened, or when it closes if it has not opened", () => {
    expect(cycleDate({ opened_at: "2026-10-01T00:00:00Z", closes_at: "2026-10-30T00:00:00Z" })).toBe("2026-10-01T00:00:00Z");
    expect(cycleDate({ opened_at: null, closes_at: "2026-10-30T00:00:00Z" })).toBe("2026-10-30T00:00:00Z");
  });

  it("warns, without refusing, when a PC goes over its allowance", () => {
    const use = { type: "elite" as const, allowance: 2, logged: 2 };
    expect(allowanceWarning({ ...use, logged: 1 }, 1, "Agnes", "November")).toBeNull();
    expect(allowanceWarning(use, 1, "Agnes", "November")).toBe("Agnes has 2 Elite actions in November, and this makes 3 logged. You can still log it.");
    // NPCs, and characters not in the cycle, have no allowance to go over.
    expect(allowanceWarning({ ...use, allowance: null }, 5, "Prince Vasquez", "November")).toBeNull();
  });

  it("keeps the date, cycle, character and type for another entry, and clears the rest", () => {
    const form: EntryFields = {
      type: "underworld",
      who: "c:1",
      name: "",
      specialization: "Transportation",
      action_key: "lockdown",
      purpose: "To lock down the docks",
      times: 2,
      blocks: 1,
      happened_at: "2026-11-14T19:00",
      cycle_id: "c1",
      needs_details: true,
    };
    expect(another(form)).toEqual({
      ...form,
      specialization: "",
      action_key: "",
      purpose: "",
      times: 1,
      blocks: 0,
      needs_details: false,
    });
  });
});
