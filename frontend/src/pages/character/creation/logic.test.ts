import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "../../../api/types";
import { detailNeed, fieldSkills } from "../fields";
import { canTapDots, choiceName, choose, clear, move, copyKey, fieldProblems, identityChoices, isRanking, keyed, keysOf, left, nextCopy, pastBudgetText, picksLeft, pointsText, seatPicks, tapDots, togglePoints, traitOf } from "./logic";

const SKILLS = { 4: 1, 3: 2, 2: 3, 1: 4 };
const ATTRIBUTES = { 7: 1, 5: 1, 3: 1 };

describe("tapDots", () => {
  // A ghoul's 5 discipline dots, as many on one discipline as it likes.
  it("sets a rating while the dots it adds are left", () => {
    expect(tapDots({ Auspex: 3 }, 5, "Celerity", 2)).toEqual({ Auspex: 3, Celerity: 2 });
  });

  it("refuses a rating the dots left cannot pay for", () => {
    const picks = { Auspex: 3 };
    expect(tapDots(picks, 5, "Celerity", 3)).toBe(picks);
    expect(canTapDots(picks, 5, "Celerity", 3)).toBe(false);
  });

  it("counts a trait's own dots as freed when it moves", () => {
    expect(canTapDots({ Auspex: 3, Celerity: 2 }, 5, "Auspex", 2)).toBe(true);
    expect(tapDots({ Auspex: 3, Celerity: 1 }, 5, "Auspex", 4)).toEqual({ Auspex: 4, Celerity: 1 });
  });

  it("clears a trait when its own rating is tapped again", () => {
    expect(tapDots({ Auspex: 3 }, 5, "Auspex", 3)).toEqual({});
  });
});

describe("choose", () => {
  it("places a trait in an empty slot", () => {
    expect(choose({}, SKILLS, 4, null, "Brawl")).toEqual({ picks: { Brawl: 4 }, key: "Brawl" });
  });

  it("puts a trait in place of the one in the slot", () => {
    expect(choose({ Brawl: 4, Dodge: 3 }, SKILLS, 4, "Brawl", "Melee").picks).toEqual({ Dodge: 3, Melee: 4 });
  });

  it("moves a trait picked at another rating, outside a ranking too", () => {
    expect(choose({ Brawl: 4 }, SKILLS, 3, null, "Brawl")).toEqual({ picks: { Brawl: 3 }, key: "Brawl", holder: null });
  });

  it("does nothing at a rating with no picks, or none left", () => {
    expect(choose({}, ATTRIBUTES, 6, null, "Physical").picks).toEqual({});
    const full = { Athletics: 3, Dodge: 3 };
    expect(choose(full, SKILLS, 3, null, "Stealth").picks).toBe(full);
  });

  it("swaps in a ranking when the trait is placed at another rating", () => {
    expect(choose({ Physical: 7, Mental: 3 }, ATTRIBUTES, 7, "Physical", "Mental").picks).toEqual({ Mental: 7, Physical: 3 });
  });

  it("moves a ranked trait to an empty slot, leaving its old one empty", () => {
    expect(choose({ Physical: 5 }, ATTRIBUTES, 7, null, "Physical").picks).toEqual({ Physical: 7 });
  });

  it("takes a ranked slot from its holder for a trait not yet placed", () => {
    expect(choose({ Physical: 7 }, ATTRIBUTES, 7, "Physical", "Social").picks).toEqual({ Social: 7 });
    expect(choose({ Dexterity: 1 }, { 1: 1 }, 1, "Dexterity", "Strength").picks).toEqual({ Strength: 1 });
  });

  it("gives a skill bought by field a key of its own the second time", () => {
    expect(choose({ Performance: 3 }, SKILLS, 1, null, "Performance", true)).toEqual({ picks: { Performance: 3, [copyKey("Performance", 2)]: 1 }, key: copyKey("Performance", 2) });
  });

  it("keeps the slot as it is when its own trait is chosen again", () => {
    const picks = { [copyKey("Performance", 2)]: 1 };
    expect(choose(picks, SKILLS, 1, copyKey("Performance", 2), "Performance", true)).toEqual({ picks, key: copyKey("Performance", 2) });
  });

  it("counts what is left", () => {
    expect(left({ Athletics: 3 }, SKILLS, 3)).toBe(1);
  });
});

describe("move", () => {
  it("moves a pick to an empty slot, leaving the one it left empty", () => {
    expect(move({ Brawl: 3, Dodge: 3 }, SKILLS, 4, null, "Brawl")).toEqual({ picks: { Dodge: 3, Brawl: 4 }, key: "Brawl", holder: null });
  });

  it("swaps with the pick in the slot when it fits where the move left", () => {
    expect(move({ Brawl: 3, Dodge: 4 }, SKILLS, 4, "Dodge", "Brawl")).toEqual({ picks: { Brawl: 4, Dodge: 3 }, key: "Brawl", holder: "swapped" });
  });

  it("takes the pick in the slot off when it can't go where the move left", () => {
    const barredAt3 = (name: string, rating: number) => !(name === "Dodge" && rating === 3);
    expect(move({ Brawl: 3, Dodge: 4 }, SKILLS, 4, "Dodge", "Brawl", barredAt3)).toEqual({ picks: { Brawl: 4 }, key: "Brawl", holder: "off" });
  });

  it("takes the pick in the slot off when the move came from beyond the slots", () => {
    // Thin Blooded took the pick at 2 away; Celerity's is kept there until it moves.
    expect(move({ Celerity: 2, Auspex: 1 }, { 1: 1 }, 1, "Auspex", "Celerity")).toEqual({ picks: { Celerity: 1 }, key: "Celerity", holder: "off" });
  });

  it("keeps a skill's field with it, as its key", () => {
    const second = copyKey("Performance", 2);
    expect(move({ Performance: 3, [second]: 1 }, SKILLS, 2, null, second).picks).toEqual({ Performance: 3, [second]: 2 });
  });

  it("does nothing at the rating it is at, or with no slot free", () => {
    const picks = { Brawl: 3, Dodge: 4 };
    expect(move(picks, SKILLS, 3, null, "Brawl").picks).toBe(picks);
    expect(move(picks, SKILLS, 4, null, "Brawl").picks).toBe(picks);
    expect(move(picks, SKILLS, 5, null, "Brawl").picks).toBe(picks);
  });
});

describe("seatPicks", () => {
  it("keeps each pick in the slot it was in", () => {
    expect(seatPicks([null, "Dodge", null], ["Dodge", "Melee"], 3)).toEqual(["Melee", "Dodge", null]);
  });

  it("empties the slot of a pick taken back", () => {
    expect(seatPicks(["Brawl", "Dodge"], ["Dodge"], 2)).toEqual([null, "Dodge"]);
  });

  it("puts picks beyond the slots after them", () => {
    expect(seatPicks([], ["Celerity", "Auspex"], 1)).toEqual(["Celerity", "Auspex"]);
    expect(seatPicks([], ["Celerity"], 0)).toEqual(["Celerity"]);
  });
});

describe("picksLeft", () => {
  it("says what is left, rating by rating", () => {
    expect(picksLeft({ Brawl: 4, Dodge: 3, Athletics: 3, Melee: 1 }, SKILLS)).toBe("6 picks left: three at 2 and three at 1");
    expect(picksLeft({ Physical: 7, Social: 5 }, ATTRIBUTES)).toBe("1 pick left: one at 3");
  });

  it("is nothing once every pick is placed", () => {
    expect(picksLeft({ Physical: 7, Social: 5, Mental: 3 }, ATTRIBUTES)).toBeNull();
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

describe("pointsText", () => {
  it("says the points used of the budget", () => {
    expect(pointsText(3, 7, false)).toBe("3 of 7 points");
    expect(pointsText(7, 7, true)).toBe("7 of 7 points");
  });

  it("says flaws past the budget count only up to it (p. 85)", () => {
    expect(pointsText(9, 7, true)).toBe("9 points, 7 count toward the budget");
    expect(pointsText(11, 10, true)).toBe("11 points, 10 count toward the budget");
    expect(pastBudgetText("Flaws", 7)).toBe("Flaws past 7 points need the Storyteller's OK, and count for nothing more (p. 85).");
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

describe("more than one field of a skill", () => {
  const fielded = (name: string) => detailNeed({ name, needs_field: ["Crafts", "Performance", "Science"].includes(name), instance: null });

  it("keys the second field apart from the first, and finds the trait again", () => {
    const key = nextCopy(["Performance"], "Performance");
    expect(key).toBe(copyKey("Performance", 2));
    expect(traitOf(key)).toBe("Performance");
    expect(traitOf("Performance")).toBe("Performance");
    expect(nextCopy(["Performance", key], "Performance")).toBe(copyKey("Performance", 3));
  });

  it("counts each field's pick against the ratings", () => {
    const { picks } = choose({ Performance: 3 }, SKILLS, 3, null, "Performance", true);
    expect(picks).toEqual({ Performance: 3, [copyKey("Performance", 2)]: 3 });
    expect(left(picks, SKILLS, 3)).toBe(0);
    expect(keysOf(picks, "Performance")).toEqual(["Performance", copyKey("Performance", 2)]);
  });

  it("gives saved fields of one skill a key each, and their fields", () => {
    const saved = keyed([
      { name: "Performance", detail: "Singing", pick: 2 },
      { name: "Brawl", detail: "", pick: 4 },
      { name: "Performance", detail: "Dance", pick: 1 },
    ]);
    expect(saved.picks).toEqual({ Brawl: 4, Performance: 2, [copyKey("Performance", 2)]: 1 });
    expect(saved.details).toEqual({ Brawl: "", Performance: "Singing", [copyKey("Performance", 2)]: "Dance" });
  });

  it("says which picks still need a field, and which repeat one", () => {
    const picks = { Brawl: 4, Performance: 2, [copyKey("Performance", 2)]: 1, Science: 3 };
    const problems = fieldProblems(picks, { Performance: "Singing", [copyKey("Performance", 2)]: " singing " }, fielded);
    expect(Object.keys(problems).sort()).toEqual([copyKey("Performance", 2), "Science"]);
    expect(problems.Science).toEqual({ message: "Science needs a field.", twice: false });
    expect(problems[copyKey("Performance", 2)]!.twice).toBe(true);
    expect(fieldProblems({ Performance: 2 }, { Performance: "Singing" }, fielded)).toEqual({});
  });

  it("asks a name of each Retainer, and a different one for the second", () => {
    const named = (name: string) => detailNeed({ name, needs_field: false, instance: name === "Retainers" ? "Retainer" : null });
    const picks = { Retainers: 3, [copyKey("Retainers", 2)]: 2, Haven: 1 };
    expect(fieldProblems(picks, { Retainers: "Bocephus" }, named)).toEqual({ [copyKey("Retainers", 2)]: { message: "Name each Retainer.", twice: false } });
    expect(fieldProblems(picks, { Retainers: "Bocephus", [copyKey("Retainers", 2)]: "bocephus" }, named)[copyKey("Retainers", 2)]).toEqual({
      message: "Retainers: bocephus is picked already; give this one another name.",
      twice: true,
    });
  });

  it("takes the skills that need a field from the rules", () => {
    const catalogue = {
      traits: [
        { category: "skills", name: "Crafts", needs_field: true },
        { category: "skills", name: "Brawl", needs_field: false },
      ],
    } as unknown as CatalogueOut;
    expect([...fieldSkills(catalogue)]).toEqual(["Crafts"]);
    expect(fieldSkills(undefined).size).toBe(0);
  });
});

describe("choiceName", () => {
  it("names a custom archetype by what its player called it", () => {
    expect(choiceName({ category: "archetype", name: "Other…", detail: "The Penitent Thief" })).toBe("The Penitent Thief");
  });

  it("keeps the listed name otherwise, or when no name was given", () => {
    expect(choiceName({ category: "archetype", name: "Fighter", detail: "" })).toBe("Fighter");
    expect(choiceName({ category: "archetype", name: "Other…", detail: " " })).toBe("Other…");
    expect(choiceName({ category: "merits", name: "Other…", detail: "x" })).toBe("Other…");
  });
});
