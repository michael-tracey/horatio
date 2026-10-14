import { describe, expect, it } from "vitest";
import { canTap, left, tap, togglePoints } from "./logic";

const SKILLS = { 4: 1, 3: 2, 2: 3, 1: 4 };
const ATTRIBUTES = { 7: 1, 5: 1, 3: 1 };

describe("tap", () => {
  it("sets a rating that has picks left", () => {
    expect(tap({}, SKILLS, "Brawl", 4)).toEqual({ Brawl: 4 });
  });

  it("clears a trait when its own rating is tapped again", () => {
    expect(tap({ Brawl: 4 }, SKILLS, "Brawl", 4)).toEqual({});
  });

  it("moves a trait to another rating", () => {
    expect(tap({ Brawl: 4 }, SKILLS, "Brawl", 3)).toEqual({ Brawl: 3 });
  });

  it("does nothing at a rating with no picks", () => {
    expect(tap({}, ATTRIBUTES, "Physical", 6)).toEqual({});
  });

  it("does nothing when a shared rating is used up", () => {
    const picks = { Athletics: 3, Dodge: 3 };
    expect(tap(picks, SKILLS, "Stealth", 3)).toBe(picks);
    expect(canTap(picks, SKILLS, "Stealth", 3)).toBe(false);
  });

  it("swaps when a single-pick rating is taken", () => {
    const picks = { Physical: 7, Mental: 3 };
    expect(tap(picks, ATTRIBUTES, "Mental", 7)).toEqual({ Mental: 7, Physical: 3 });
  });

  it("takes a single pick from a trait that had none, clearing the old holder", () => {
    expect(tap({ Physical: 7 }, ATTRIBUTES, "Social", 7)).toEqual({ Social: 7 });
  });

  it("counts what is left", () => {
    expect(left({ Athletics: 3 }, SKILLS, 3)).toBe(1);
  });
});

describe("togglePoints", () => {
  it("adds within the budget and refuses past it", () => {
    const picks = togglePoints({}, 7, "Abyssal Horror", 3);
    expect(picks).toEqual({ "Abyssal Horror": 3 });
    expect(togglePoints(picks, 7, "Additional Uncommon Discipline", 5)).toBe(picks);
  });

  it("removes on a second toggle", () => {
    expect(togglePoints({ "Acute Sense": 1 }, 7, "Acute Sense", 1)).toEqual({});
  });
});
