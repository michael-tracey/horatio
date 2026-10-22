import { describe, expect, it } from "vitest";
import { costText, lastsText, targeted } from "./influenceEffects";

const dates = { date: (at: Date | string) => new Date(at).toISOString().slice(0, 10) };
const now = new Date("2026-10-21T12:00:00Z");

describe("targeted", () => {
  it("is Attack, Block, Boost and Defend", () => {
    expect(["attack", "block", "boost", "defend"].every(targeted)).toBe(true);
    expect(targeted("discovery_block")).toBe(false);
    expect(targeted(null)).toBe(false);
  });
});

describe("lastsText", () => {
  it("gives the date, and the games when they may run longer", () => {
    expect(lastsText({ ends_at: "2026-11-21T12:00:00Z", games_left: 0 }, dates, now)).toBe("until 2026-11-21");
    expect(lastsText({ ends_at: "2026-11-21T12:00:00Z", games_left: 2 }, dates, now)).toBe("until 2026-11-21, or 2 more games if that is later");
  });

  it("gives only the games once the date is past", () => {
    expect(lastsText({ ends_at: "2026-10-01T12:00:00Z", games_left: 1 }, dates, now)).toBe("until 1 more game is played");
    expect(lastsText({ ends_at: "2026-10-01T12:00:00Z", games_left: 2 }, dates, now)).toBe("until 2 more games are played");
  });
});

describe("costText", () => {
  it("shows an attack's cost a level", () => {
    expect(costText({ kind: "attack", levels: 2, cost: 6, per_level: 3, spent: 4 }, "E3")).toBe("2 levels at 3 actions each: 6 actions. E3 spent 4.");
  });

  it("shows a boost's cost, and a block's strength", () => {
    expect(costText({ kind: "boost", levels: 1, cost: 5, per_level: 0, spent: 5 }, "UW2")).toBe("1 level: 5 actions. UW2 spent 5.");
    expect(costText({ kind: "block", levels: 5, cost: 0, per_level: 0, spent: 1 }, "UW2")).toBe("Strength 5.");
  });
});
