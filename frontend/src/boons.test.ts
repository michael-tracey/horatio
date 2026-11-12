import { describe, expect, it } from "vitest";
import { actionsFor, changeText, countsText, emptyRow, owes, partyName, rowsTotal, stateText } from "./boons";

const party = (name: string, standing: "active" | "final_death" | "off_field" | null = "active") => ({
  character_id: standing ? "c1" : null,
  name,
  kind: standing ? "pc" : null,
  standing,
});

describe("boons", () => {
  it("names who owes whom, with how a party left play", () => {
    expect(owes({ debtor: party("Agnes"), creditor: party("Bram") })).toBe("Agnes owes Bram");
    expect(partyName(party("Mercer", "final_death"))).toBe("Mercer (Final Death)");
    expect(partyName(party("Grove", null))).toBe("Grove");
  });

  it("says where a boon stands", () => {
    expect(stateText({ state: "registered", settled_how: null, departed: false })).toBe("");
    expect(stateText({ state: "registered", settled_how: null, departed: true })).toBe("Involves someone departed");
    expect(
      stateText({
        state: "settled",
        settled_how: "called_in",
        departed: false,
      }),
    ).toBe("Settled: called in");
    expect(stateText({ state: "void", settled_how: null, departed: false })).toBe("Void");
  });

  it("reads a change in the log", () => {
    expect(changeText({ field: "kind", before: "Minor", after: "Major" })).toBe("Kind: Minor → Major");
    expect(changeText({ field: "conditions", before: "", after: "No trading" })).toBe("Conditions: (none) → No trading");
  });

  it("sums standing boons by kind", () => {
    expect(countsText([])).toBe("none");
    expect(
      countsText([
        { kind: "minor", count: 2 },
        { kind: "major", count: 1 },
      ]),
    ).toBe("2 minor, 1 major");
  });

  it("offers the actions a boon's state allows", () => {
    expect(actionsFor("registered")).toEqual(["edit", "trade", "pass", "settle", "void"]);
    expect(actionsFor("settled")).toEqual(["edit", "void", "reopen"]);
    expect(actionsFor("void")).toEqual(["edit", "reopen"]);
  });

  it("counts what the quick entry's rows make, leaving out untouched rows", () => {
    const filled = {
      ...emptyRow("2026-10-03"),
      debtor: { who: "c:1", name: "" },
      count: 3,
    };
    expect(rowsTotal([filled, emptyRow("2026-10-03"), { ...filled, count: 1 }])).toBe(4);
  });
});
