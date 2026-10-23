import { describe, expect, it } from "vitest";
import type { TraitOut } from "../../api/types";
import { foundElsewhere, openToYou, shownChips, type Choices } from "./choices";

const trait = (category: string, name: string) => ({ category, name }) as unknown as TraitOut;

const choices = (key: string, name: string, traits: string[], canTake: string[], held = 0): Choices => {
  const all = traits.map((t) => trait(key, t));
  return { key, name, traits: all, refused: {}, canTake: all.filter((t) => canTake.includes(t.name)), held, ready: true };
};

const DISCIPLINES = choices("disciplines", "Disciplines", ["Celerity", "Potence"], ["Celerity"], 2);
const TECHNIQUES = choices("techniques", "Techniques", ["Fearful Blow", "Rapid Reflexes"], ["Fearful Blow", "Rapid Reflexes"]);
const ELDER = choices("elder_disciplines", "Elder Disciplines", ["Celerity: Projectile"], []);
const RITUALS = choices("rituals", "Rituals", ["Thaumaturgy: Blood Mastery"], []);

describe("the line pointing to powers", () => {
  it("names categories held nothing in with something to take, not the first", () => {
    expect(openToYou([DISCIPLINES, TECHNIQUES, ELDER, RITUALS]).map((c) => c.key)).toEqual(["techniques"]);
  });

  it("goes once one is held", () => {
    expect(openToYou([DISCIPLINES, { ...TECHNIQUES, held: 1 }])).toEqual([]);
  });
});

describe("the chips", () => {
  it("show every category, but rituals only once open", () => {
    expect(shownChips([DISCIPLINES, TECHNIQUES, ELDER, RITUALS], "disciplines").map((c) => c.key)).toEqual(["disciplines", "techniques", "elder_disciplines"]);
    const open = { ...RITUALS, canTake: RITUALS.traits };
    expect(shownChips([DISCIPLINES, open], "disciplines").map((c) => c.key)).toEqual(["disciplines", "rituals"]);
    expect(shownChips([DISCIPLINES, { ...RITUALS, held: 1 }], "disciplines").map((c) => c.key)).toEqual(["disciplines", "rituals"]);
  });
});

describe("searching the whole part", () => {
  it("finds a power in another category, and says whether it can be taken", () => {
    const found = foundElsewhere([DISCIPLINES, TECHNIQUES, ELDER], "disciplines", "fearful", []);
    expect(found.map((f) => [f.category.key, f.trait.name, f.canTake])).toEqual([["techniques", "Fearful Blow", true]]);
    expect(foundElsewhere([DISCIPLINES, ELDER], "disciplines", "projectile", [])[0]?.canTake).toBe(false);
  });

  it("leaves out what is held", () => {
    expect(foundElsewhere([DISCIPLINES, TECHNIQUES], "disciplines", "fearful", [{ category: "techniques", name: "Fearful Blow", detail: "" }])).toEqual([]);
  });
});
