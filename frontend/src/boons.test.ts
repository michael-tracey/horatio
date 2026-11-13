import { describe, expect, it } from "vitest";
import { actionsFor, appealText, changeText, countsText, emptyRow, eventName, flagBody, flagText, LOSS_TEXT, owes, partyName, rowsTotal, stateText, voidsText, type BoonFlag } from "./boons";

const party = (name: string, standing: "active" | "final_death" | "off_field" | null = "active") => ({
  character_id: standing ? "c1" : null,
  name,
  kind: standing ? "pc" : null,
  standing,
  boonbreaker: false,
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

  it("words the review's flags (#687)", () => {
    const parties = {
      debtor: { character_id: "c1", name: "Agnes", kind: "pc", standing: "active" as const, boonbreaker: false },
      creditor: { character_id: null, name: "The Moon", kind: null, standing: null, boonbreaker: false },
    };
    const flag = (over: Partial<BoonFlag>): BoonFlag => ({
      id: "f1",
      kind: "unmatched",
      side: "creditor",
      detail: "No character in the troupe has this name.",
      note: "",
      other_boon_id: null,
      raised_by: null,
      raised_at: "2026-10-03T20:00:00Z",
      ...over,
    });
    expect(flagText(flag({}), parties)).toBe("Name not linked (creditor, The Moon): No character in the troupe has this name.");
    expect(flagBody(flag({}), parties)).toBe("creditor, The Moon: No character in the troupe has this name.");
    expect(flagText(flag({ kind: "duplicate", side: null, detail: "Like Agnes's minor boon." }), parties)).toBe("Likely duplicate: Like Agnes's minor boon.");
    expect(flagText(flag({ kind: "hand", side: null, note: "A precedent?", raised_by: "Sam" }), parties)).toBe("Flagged by Sam: A precedent?");
    expect(flagText(flag({ kind: "hand", side: null, note: "A precedent?" }), parties)).toBe("Flagged: A precedent?");
    expect(eventName("rejected")).toBe("Not accepted");
  });
});

describe("Boonbreakers (#717)", () => {
  it("says what a declaration makes void before it's done", () => {
    expect(voidsText({ owed_by: 2, owed_to: 1 })).toBe("This makes 3 boons void: 2 owed by them, 1 owed to them.");
    expect(voidsText({ owed_by: 1, owed_to: 0 })).toBe("This makes 1 boon void: 1 owed by them, 0 owed to them.");
    expect(voidsText({ owed_by: 0, owed_to: 0 })).toBe("They have no open boons to make void.");
  });

  it("names each appeal for mercy, with a court's votes against", () => {
    expect(appealText({ to: "harpy", outcome: "granted", against: null })).toBe("To the Harpy: mercy granted");
    expect(appealText({ to: "court", outcome: "refused", against: 4 })).toBe("To a court of Harpies: mercy refused, 4 against");
    expect(appealText({ to: "court", outcome: "granted", against: 0 })).toBe("To a court of Harpies: mercy granted, 0 against");
  });

  it("says what is owed for ignoring a great boon", () => {
    expect(LOSS_TEXT.due).toContain("p. 395");
    expect(LOSS_TEXT.waived).toBe("No status was taken for ignoring it.");
  });
});
