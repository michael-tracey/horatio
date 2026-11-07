import { describe, expect, it } from "vitest";
import { changedText } from "./backgroundChanges";

const dates = { date: (at: Date | string) => new Date(at).toISOString().slice(0, 10) };
const starts = "2026-11-07T12:00:00Z";
const crafts = { source: "crafts", delta: 1, starts_at: starts, ends_at: null, games_left: 0 };

describe("changedText", () => {
  it("says a month's boost and where it came from", () => {
    expect(changedText({ trait: "Resources", rating: 2, now: 3, changes: [crafts] }, dates)).toBe("Resources 3 (+1 this month, Crafts)");
  });

  it("says how long overtaxed Resources take to come back", () => {
    const overtaxed = { source: "overtaxed", delta: -2, starts_at: starts, ends_at: "2027-02-07T12:00:00Z", games_left: 6 };
    expect(changedText({ trait: "Resources", rating: 3, now: 2, changes: [crafts, overtaxed] }, dates, new Date(starts))).toBe(
      "Resources 2 (+1 this month, Crafts; −2 overtaxed, until 2027-02-07, or 6 more games if that is later)",
    );
  });
});
