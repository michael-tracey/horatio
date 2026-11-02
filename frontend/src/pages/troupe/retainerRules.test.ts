import { describe, expect, it } from "vitest";
import { bodyOf, DEFAULT_GROWTH, DEFAULT_UPKEEP, draftOf, draftProblem } from "./retainerRules";

const OFF = { upkeep: null, growth: null, upkeep_text: null, growth_text: null };

describe("retainer rules (#442)", () => {
  it("start off, with figures ready for switching on", () => {
    const draft = draftOf(OFF);
    expect(draft).toEqual({ upkeepOn: false, upkeep: DEFAULT_UPKEEP, growthOn: false, growth: DEFAULT_GROWTH });
    expect(bodyOf(draft)).toEqual({ upkeep: null, growth: null });
  });

  it("save a game's upkeep without a month to choose, and a month's with it", () => {
    const draft = { ...draftOf(OFF), upkeepOn: true, upkeep: { ...DEFAULT_UPKEEP, month_at: "downtime" as const } };
    expect(bodyOf(draft).upkeep?.month_at).toBe("game");
    const monthly = { ...draft, upkeep: { ...draft.upkeep, per: "month" as const } };
    expect(bodyOf(monthly).upkeep).toEqual({ amount: 1, pool: "blood", ghouls_only: false, per: "month", month_at: "downtime" });
  });

  it("leave out a rule switched off, keeping its figures in the form", () => {
    const saved = { ...OFF, upkeep: { ...DEFAULT_UPKEEP, amount: 2, pool: "willpower" as const }, growth: 4 };
    const draft = { ...draftOf(saved), upkeepOn: false };
    expect(bodyOf(draft)).toEqual({ upkeep: null, growth: 4 });
    expect(draft.upkeep.amount).toBe(2);
  });

  it("say what is wrong with a figure out of range", () => {
    const draft = { ...draftOf(OFF), upkeepOn: true, upkeep: { ...DEFAULT_UPKEEP, amount: 0 } };
    expect(draftProblem(draft)).toBe("Upkeep is from 1 to 10 for each Retainer.");
    expect(draftProblem({ ...draft, upkeepOn: false, growthOn: true, growth: 2.5 })).toBe("Growth is from 1 to 20 XP a month.");
    expect(draftProblem({ ...draft, upkeepOn: false })).toBeNull();
  });
});
