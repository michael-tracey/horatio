import { describe, expect, it } from "vitest";
import type { CatalogueOut, CreationOut, PoolOut, SheetOut, SheetTraitOut } from "../../../api/types";
import { freedPicks, givenIn, takenAway, unchosenFree } from "./gifts";
import { brokenChecks, type StepRef } from "./notices";

const STEPS: StepRef[] = [
  { key: "concept", title: "Concept", categories: [], decides: ["clan"] },
  { key: "skills", title: "Skills", categories: ["skills"], decides: ["lore_specializations"] },
  { key: "backgrounds", title: "Backgrounds", categories: ["backgrounds"] },
  { key: "merits", title: "Merits & flaws", categories: ["merits", "flaws"] },
  { key: "review", title: "Review", categories: [] },
];

function pool(over: Partial<PoolOut>): PoolOut {
  return { category: "backgrounds", category_name: "Backgrounds", rating: 3, kind: "picks", allowed: 1, used: 1, remaining: 0, restriction: null, options: null, without_dot: [], because: [], traits: [], ...over };
}

function trait(category: string, name: string, over: Partial<SheetTraitOut> = {}): SheetTraitOut {
  return { id: name, category, category_name: category, group: "", name, detail: "", rating: 1, free_rating: 1, min_rating: 0, pending_from: null, granted_rating: 0, granted_by: [], note: "", ...over };
}

const sheet = (traits: SheetTraitOut[], problems: SheetOut["problems"] = []) => ({ traits, problems }) as SheetOut;
const creation = (pools: PoolOut[], given: CreationOut["given"] = []): CreationOut => ({ complete: false, pools, needs: [], path_starts: [], budget_changes: [], given });

describe("freedPicks", () => {
  it("marks a pick a merit now makes free, where it was placed and on Merits", () => {
    const herd = { name: "Herd", detail: "", pick: 3, fits: true, because: [], freed_by: [{ category: "merits", name: "Personal Cult" }] };

    expect(freedPicks({ creation: creation([pool({ traits: [herd] })]), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "freed/backgrounds/Herd/",
        message: "Personal Cult makes Herd free: your pick on Herd can go elsewhere.",
        on: ["backgrounds", "merits"],
        fix: "backgrounds",
        trait: { category: "backgrounds", name: "Herd" },
      },
    ]);
  });

  it("says nothing of a pick still worth its dots", () => {
    const fame = { name: "Fame", detail: "", pick: 3, fits: true, because: [], freed_by: [] };

    expect(freedPicks({ creation: creation([pool({ traits: [fame] })]), sheet: sheet([]), steps: STEPS })).toEqual([]);
  });
});

describe("unchosenFree", () => {
  const offer = (over: object) => ({
    grant: "g",
    category: "backgrounds",
    category_name: "Backgrounds",
    options: [],
    places: [4, 3, 2],
    count: null,
    points: null,
    picks: [],
    complete: false,
    locked: null,
    ...over,
  });
  const royalty = (over: object) => trait("merits", "Ventrue Royalty", { rating: 2, free_choices: [offer(over)] });

  it("asks for a merit's free traits where they land, and on Merits", () => {
    expect(unchosenFree({ creation: creation([]), sheet: sheet([royalty({})]), steps: STEPS })).toEqual([
      { key: "free/merits/Ventrue Royalty/", message: "Ventrue Royalty: choose the backgrounds it gives. This can wait until a home troupe accepts the character.", on: ["backgrounds", "merits"], fix: "backgrounds", canWait: true },
    ]);
  });

  it("lands specialisations on Skills, with one notice for all of a merit's", () => {
    const chosen = trait("merits", "Chosen of Cappadocius", {
      free_choices: [offer({ category: "lore_specializations", category_name: "Lore Specializations", places: null }), offer({ grant: "h", category: "linguistics_specializations", category_name: "Languages", places: null })],
    });

    const [notice] = unchosenFree({ creation: creation([]), sheet: sheet([chosen]), steps: STEPS });

    expect(notice?.message).toBe("Chosen of Cappadocius: choose the lore specializations and languages it gives. This can wait until a home troupe accepts the character.");
    expect(notice?.on).toEqual(["skills", "merits"]);
  });

  it("is quiet once everything is chosen", () => {
    expect(unchosenFree({ creation: creation([]), sheet: sheet([royalty({ complete: true })]), steps: STEPS })).toEqual([]);
  });
});

describe("givenIn", () => {
  it("says whose a held trait is", () => {
    const given = [{ category: "backgrounds", name: "Fame", detail: "", rating: 2, because: [{ category: "merits", name: "Diva" }] }];

    expect(givenIn(creation([], given), "backgrounds")).toEqual({ Fame: { rating: 2, text: "Diva gives you Fame 2 free." } });
    expect(givenIn(creation([], given), "skills")).toEqual({});
  });
});

describe("brokenChecks naming a clash", () => {
  it("names the pick a flaw clashes with", () => {
    const archaic = { category: "flaws", name: "Archaic", strength: "refuse", message: "An Archaic character cannot have Computer.", looks_at: [{ category: "skills", name: "Computer" }] };
    const held = sheet([trait("skills", "Computer")], [archaic]);

    expect(brokenChecks({ creation: creation([]), sheet: held, steps: STEPS })[0]).toMatchObject({
      message: "Archaic and Computer clash: An Archaic character cannot have Computer.",
      on: ["skills", "merits"],
      fix: "skills",
    });
  });
});

describe("brokenChecks keeping a need's own words", () => {
  it("does not call a check the player must meet a clash", () => {
    const vestiges = { category: "merits", name: "Vestiges of Greatness", strength: "complete", message: "Vestiges of Greatness: choose one.", looks_at: [{ category: "skills", name: "Computer" }] };
    const held = sheet([trait("skills", "Computer")], [vestiges]);

    expect(brokenChecks({ creation: creation([]), sheet: held, steps: STEPS })[0]?.message).toBe("Vestiges of Greatness: choose one.");
  });
});

describe("takenAway", () => {
  const stolen = { category: "flaws", name: "Stolen Potential" };
  const catalogue = {
    categories: [{ key: "focus_mentals", name: "Mental Focus" }],
    traits: [{ category: "flaws", name: "Stolen Potential", page_reference: "265" }],
  } as CatalogueOut;
  const focus = (category: string) => pool({ category, rating: 1, used: 0, remaining: 1 });

  it("says why a category left with no picks is not on its step", () => {
    const left = { ...creation([focus("focus_physicals"), focus("focus_socials")]), budget_changes: [{ category: "focus_mentals", because: [stolen] }] };

    expect(takenAway(left, catalogue, ["focus_mentals"])).toEqual(["Stolen Potential: no Mental focus (p. 265)."]);
  });

  it("names the book when the page is not the core book's", () => {
    const supplement = { ...catalogue, traits: [{ category: "flaws", name: "Stolen Potential", page_reference: "Vol. 2, p. 269" }] } as CatalogueOut;
    const left = { ...creation([focus("focus_physicals")]), budget_changes: [{ category: "focus_mentals", because: [stolen] }] };

    expect(takenAway(left, supplement, ["focus_mentals"])).toEqual(["Stolen Potential: no Mental focus (Vol. 2, p. 269)."]);
  });

  it("says nothing of a category that still has its picks, or keeps one to take back", () => {
    const kept = { ...creation([focus("focus_mentals")]), budget_changes: [{ category: "focus_mentals", because: [stolen] }] };

    expect(takenAway(kept, catalogue, ["focus_mentals"])).toEqual([]);
    expect(takenAway(creation([]), catalogue, ["focus_mentals"])).toEqual([]);
  });
});
