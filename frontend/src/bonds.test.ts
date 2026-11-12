import { describe, expect, it } from "vitest";
import type { BondOut } from "./api/types";
import { BOND_SETTINGS, groupBonds, levelName, levelText, partyIn, reportedText, reportLine, reportState, statusText, untold, watched } from "./bonds";

const bond = (id: string, thrall: string, regnant: string, status = "active", level = 1): BondOut => ({
  id,
  thrall: { character_id: thrall === "Lady Ophelia" ? null : `c-${thrall}`, name: thrall, kind: thrall === "Lady Ophelia" ? null : "pc" },
  regnant: { character_id: `c-${regnant}`, name: regnant, kind: "pc" },
  level,
  status,
  known_to_regnant: false,
  ended_at: null,
  ended_reason: "",
  fades_on: null,
  fade_reason: "",
  thrall_told: false,
  kept_for_regnant: false,
  last_drink: null,
  entries: [],
});

describe("fading bonds (#662)", () => {
  it("keeps on staff's list what a player still sees as it was", () => {
    const faded = { ...bond("1", "Agnes", "Bram", "ended"), fade_reason: "regnant_died" };
    expect(untold(faded)).toBe(true);
    expect(watched(faded)).toBe(true);
    expect(untold({ ...faded, thrall_told: true })).toBe(false);
    expect(watched({ ...faded, thrall_told: true })).toBe(false);
    expect(watched(bond("2", "Agnes", "Bram", "fading"))).toBe(true);
    expect(watched({ ...bond("3", "Agnes", "Bram", "ended"), kept_for_regnant: true })).toBe(true);
    expect(watched(bond("4", "Agnes", "Bram", "broken"))).toBe(false);
  });
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

describe("drinks players report", () => {
  const report = {
    thrall: { character_id: "a", name: "Agnes", kind: "pc" },
    regnant: { character_id: "b", name: "Bram", kind: "pc" },
    reason: "",
  } as const;

  it("reads as the drink, and where it stands", () => {
    expect(reportLine(report, "3 Nov 2026")).toBe("Agnes drank Bram's blood on 3 Nov 2026");
    expect(reportState({ ...report, status: "pending", waiting_on: "staff" })).toBe("Waiting for the storytellers");
    expect(reportState({ ...report, status: "pending", waiting_on: "thrall" })).toBe("Waiting for Agnes's player to confirm");
    expect(reportState({ ...report, status: "approved", waiting_on: "staff" })).toBe("Counted");
    expect(reportState({ ...report, status: "declined", waiting_on: "staff", reason: "Not at that game." })).toBe("Declined: Not at that game.");
    expect(reportState({ ...report, status: "declined", waiting_on: "thrall" })).toBe("Declined");
  });

  it("says what became of a drink just reported", () => {
    expect(reportedText("recorded", 2, "Agnes")).toBe("Recorded: second drink.");
    expect(reportedText("staff", null, "Agnes")).toBe("Sent to the storytellers to approve.");
    expect(reportedText("thrall", null, "Agnes")).toBe("Sent to Agnes's player to confirm.");
  });

  it("offers every setting, the player modes among them", () => {
    expect(BOND_SETTINGS.map((s) => s.value)).toEqual(["off", "staff", "players_report", "players_manage"]);
  });
});
