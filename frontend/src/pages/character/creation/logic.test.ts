import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "../../../api/types";
import { canTap, clear, identityChoices, isRanking, left, tap, togglePoints } from "./logic";

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

  it("does not swap a single pick that is not a ranking", () => {
    // Skills have one 4 among many ratings: once used, it greys out like the rest.
    const picks = { Brawl: 4 };
    expect(canTap(picks, SKILLS, "Dodge", 4)).toBe(false);
    expect(tap(picks, SKILLS, "Dodge", 4)).toBe(picks);
    expect(canTap(picks, SKILLS, "Brawl", 4)).toBe(true);
  });

  it("swaps a single focus, since one pick is a ranking", () => {
    expect(tap({ Dexterity: 1 }, { 1: 1 }, "Strength", 1)).toEqual({ Strength: 1 });
  });

  it("counts what is left", () => {
    expect(left({ Athletics: 3 }, SKILLS, 3)).toBe(1);
  });
});

describe("isRanking", () => {
  it("is a ranking when every rating has one pick", () => {
    expect(isRanking(ATTRIBUTES)).toBe(true);
    expect(isRanking(SKILLS)).toBe(false);
    expect(isRanking({ 2: 1, 1: 2 })).toBe(false);
  });
});

describe("clear", () => {
  it("takes a row's pick back", () => {
    expect(clear({ Brawl: 4, Dodge: 3 }, "Brawl")).toEqual({ Dodge: 3 });
  });

  it("leaves picks alone for a row with none", () => {
    const picks = { Dodge: 3 };
    expect(clear(picks, "Brawl")).toBe(picks);
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

describe("identityChoices", () => {
  const catalogue = {
    categories: [
      { key: "sect", name: "Sect", group: "Identity", rated: false, max_rating: null },
      { key: "faction", name: "Faction", group: "Identity", rated: false, max_rating: null, requires: { category: "sect", name: "Sabbat" } },
      { key: "skills", name: "Skills", group: "Abilities", rated: true, max_rating: 5 },
    ],
    traits: [
      { category: "sect", name: "Sabbat" },
      { category: "sect", name: "Camarilla" },
      { category: "faction", name: "Orthodox" },
      { category: "skills", name: "Brawl" },
    ],
  } as unknown as CatalogueOut;
  const keys = (traits: { category: string; name: string }[]) => identityChoices(catalogue, { traits }).map((c) => c.key);

  it("offers faction only to the Sabbat", () => {
    expect(keys([])).toEqual(["sect"]);
    expect(keys([{ category: "sect", name: "Camarilla" }])).toEqual(["sect"]);
    expect(keys([{ category: "sect", name: "Sabbat" }])).toEqual(["sect", "faction"]);
  });
});
