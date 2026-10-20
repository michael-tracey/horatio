import { describe, expect, it } from "vitest";
import { joining, makeUp } from "./xpRange";

const fresh = { starting_xp: 30, floor: 30, ceiling: 30, games: 0, game_xp: 0, downtimes: 0, downtime_xp: 0, set_floor: 0, set_ceiling: 0 };

describe("the floor and ceiling in words", () => {
  it("is just the starting XP for a new troupe", () => {
    expect(makeUp(fresh)).toEqual({ floor: "30 starting", ceiling: "30 starting" });
  });

  it("adds games to both, downtimes to the ceiling, and what was set by hand", () => {
    const r = { ...fresh, floor: 116, ceiling: 140, games: 12, game_xp: 96, downtimes: 1, downtime_xp: 2, set_floor: -10, set_ceiling: 12 };
    expect(makeUp(r)).toEqual({
      floor: "30 starting + 96 from 12 games − 10 set by hand",
      ceiling: "30 starting + 96 from 12 games + 2 from 1 downtime + 12 set by hand",
    });
  });
});

describe("a character's XP as it joins", () => {
  const review = { given: 55, self_entered: 25, floor: 100, ceiling: 120, top_up_asked: true };
  const keep = { self_entered: "keep", top_up: null, above_ceiling: "keep", extra: 0 } as const;

  it("tops up to the floor as the player asked", () => {
    expect(joining(review, keep)).toMatchObject({ below: 45, toppedUp: 45, after: 100 });
    expect(joining({ ...review, top_up_asked: false }, keep)).toMatchObject({ toppedUp: 0, after: 55 });
  });

  it("measures the floor after self-entered XP is removed", () => {
    expect(joining(review, { ...keep, self_entered: "remove" })).toMatchObject({ removed: 25, toppedUp: 70, after: 100 });
  });

  it("keeps XP above the ceiling unless told to remove it", () => {
    const above = { ...review, floor: 30, ceiling: 40 };
    expect(joining(above, keep)).toMatchObject({ above: 15, capped: 0, after: 55 });
    expect(joining(above, { ...keep, above_ceiling: "remove", extra: 5 })).toMatchObject({ capped: 15, after: 45 });
  });
});
