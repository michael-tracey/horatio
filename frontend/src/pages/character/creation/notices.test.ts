import { describe, expect, it } from "vitest";
import type { CreationOut, PoolOut, SheetOut, SheetTraitOut } from "../../../api/types";
import { inClanChoice, inClanChoices } from "./inClan";
import { brokenChecks, stepNotices, strayPicks, type StepRef } from "./notices";

const STEPS: StepRef[] = [
  { key: "concept", title: "Concept", categories: [], decides: ["clan", "extra_in_clan_disciplines"] },
  { key: "skills", title: "Skills", categories: ["skills"] },
  { key: "disciplines", title: "Disciplines", categories: ["disciplines"] },
  { key: "merits", title: "Merits & flaws", categories: ["merits", "flaws"] },
  { key: "review", title: "Review", categories: [] },
];

function pool(over: Partial<PoolOut>): PoolOut {
  return { category: "disciplines", category_name: "Disciplines", rating: 1, kind: "picks", allowed: 1, used: 0, remaining: 1, restriction: null, options: null, traits: [], ...over };
}

function trait(category: string, name: string, over: Partial<SheetTraitOut> = {}): SheetTraitOut {
  return { id: name, category, category_name: category, group: "", name, detail: "", rating: 1, free_rating: 1, min_rating: 0, pending_from: null, granted_rating: 0, granted_by: [], note: "", ...over };
}

function sheet(traits: SheetTraitOut[], problems: SheetOut["problems"] = []): SheetOut {
  return { traits, problems } as SheetOut;
}

const creation = (pools: PoolOut[], needs: CreationOut["needs"] = []): CreationOut => ({ complete: false, pools, needs });

describe("strayPicks", () => {
  it("marks a starting dot on a discipline that is no longer in-clan, on Concept and on Disciplines", () => {
    const pools = [pool({ rating: 2, restriction: "in_clan", traits: [{ name: "Celerity", detail: "", pick: 2, fits: false }] })];

    expect(strayPicks({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "stray/disciplines/Celerity/",
        message: "Your starting dots in Celerity need moving: it is no longer in-clan.",
        on: ["concept", "disciplines"],
        fix: "disciplines",
        trait: { category: "disciplines", name: "Celerity" },
      },
    ]);
  });

  it("says nothing of picks that fit", () => {
    const pools = [pool({ restriction: "in_clan", traits: [{ name: "Auspex", detail: "", pick: 1, fits: true }] })];

    expect(strayPicks({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([]);
  });
});

describe("brokenChecks", () => {
  const vestiges = {
    category: "merits",
    name: "Vestiges of Greatness",
    strength: "complete",
    message: "Vestiges of Greatness: choose one…",
    looks_at: [{ category: "extra_in_clan_disciplines", name: null }],
  };

  it("shows a check on the steps of what it is about and what it looks at, fixed on the earliest", () => {
    expect(brokenChecks({ creation: creation([]), sheet: sheet([], [vestiges]), steps: STEPS })).toEqual([
      { key: `check/${vestiges.message}`, message: vestiges.message, on: ["concept", "merits"], fix: "concept" },
    ]);
  });

  it("leaves a step's own need, and notes, to the step", () => {
    const generation = { category: "backgrounds", name: "Generation", strength: "complete", message: "Generation, please.", looks_at: [] };
    const skills = { ...generation, category: "skills", name: "Crafts" };
    const note = { ...vestiges, strength: "note" };
    const needs = [{ step: "skills", message: "Generation, please." }];

    expect(brokenChecks({ creation: creation([], needs), sheet: sheet([], [skills, note]), steps: STEPS })).toEqual([]);
  });
});

describe("inClanChoice", () => {
  const caitiff = trait("clan", "Caitiff", { rating: null });

  it("asks a Caitiff for three, and says so", () => {
    const choice = inClanChoice(sheet([caitiff, trait("extra_in_clan_disciplines", "Auspex")]));

    expect(choice.chooses).toBe(3);
    expect(choice.chosen.map((t) => t.name)).toEqual(["Auspex"]);
    expect(choice.lines).toEqual(["Caitiff choose their three in-clan disciplines from the common ones."]);
  });

  it("follows Vestiges of Greatness", () => {
    const choice = inClanChoice(sheet([caitiff, trait("merits", "Vestiges of Greatness", { rating: 3 })]));

    expect(choice.lines).toEqual(["Two from the common ones and one from the uncommon ones (Vestiges of Greatness)."]);
  });

  it("gives any clan one with a merit that adds one, and counts a given one as held", () => {
    const choice = inClanChoice(
      sheet([
        trait("clan", "Brujah", { rating: null }),
        trait("merits", "Additional Uncommon Discipline", { rating: 5 }),
        trait("extra_in_clan_disciplines", "Potence", { granted_rating: 1, granted_by: ["Strength of Honor"] }),
      ]),
    );

    expect(choice.chooses).toBe(1);
    expect(choice.chosen).toEqual([]);
    expect(choice.given.map((t) => t.name)).toEqual(["Potence"]);
    expect(choice.lines).toEqual(["One extra in-clan discipline from the uncommon ones (Additional Uncommon Discipline)."]);
  });

  it("asks nothing of a clan without such a merit", () => {
    expect(inClanChoice(sheet([trait("clan", "Brujah", { rating: null })])).chooses).toBe(0);
  });
});

describe("inClanChoices", () => {
  it("asks for the one a merit adds on Concept and on Merits", () => {
    const traits = [trait("clan", "Brujah", { rating: null }), trait("merits", "Additional Uncommon Discipline", { rating: 5 })];

    expect(inClanChoices({ creation: creation([]), sheet: sheet(traits), steps: STEPS })).toEqual([
      { key: "in-clan/choose", message: "Additional Uncommon Discipline: choose the in-clan discipline it adds.", on: ["concept", "merits"], fix: "concept" },
    ]);
  });

  it("counts what a Caitiff has left to choose", () => {
    const traits = [trait("clan", "Caitiff", { rating: null }), trait("extra_in_clan_disciplines", "Auspex")];

    expect(inClanChoices({ creation: creation([]), sheet: sheet(traits), steps: STEPS })[0]?.message).toBe("Choose 2 more in-clan disciplines.");
  });
});

describe("stepNotices", () => {
  it("gives each message once", () => {
    const twice = () => [{ key: "a", message: "Same.", on: ["concept"], fix: "concept" }];

    expect(stepNotices({ creation: creation([]), sheet: sheet([]), steps: STEPS }, [twice, twice])).toHaveLength(1);
  });
});
