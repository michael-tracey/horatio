import { describe, expect, it } from "vitest";
import type { CatalogueOut, TeacherRuleOut } from "../../api/types";
import { EMPTY, EXAMPLES, draftOf, ruleAbout, teachable, toBody, willpowerText, type Draft } from "./teacherRules";

const body = (draft: Draft) => {
  const built = toBody(draft);
  if (!("body" in built)) throw new Error(built.problem);
  return built.body;
};

const example = (start: string) => EXAMPLES.find((x) => x.label.startsWith(start))!.draft;

describe("the issue's examples", () => {
  it("builds Lore specialisations after creation, with a downtime action", () => {
    expect(body(example("Lore specialisations"))).toEqual({
      splat: "vampire",
      category: "lore_specializations",
      names: [],
      name_prefix: null,
      condition: null,
      always: false,
      holds: "same",
      rating: null,
      actions: 1,
      willpower: 0,
      games: 0,
    });
  });

  it("builds Lore dots, always, from a teacher with the rating learned", () => {
    expect(body(example("Lore dots"))).toMatchObject({ category: "skills", names: ["Lore"], always: true, holds: "same", condition: null });
  });

  it("builds elders' modern skills, for a Willpower back after two games", () => {
    expect(body(example("Elders'"))).toMatchObject({
      category: "skills",
      names: ["Computer", "Drive", "Firearms"],
      condition: { generation: { gte: 3 } },
      always: false,
      willpower: 1,
      games: 2,
    });
  });
});

describe("toBody", () => {
  it("asks for the traits, or the prefix", () => {
    expect(toBody({ ...EMPTY, how: "traits", names: [] })).toEqual({ problem: "Choose at least one trait." });
    expect(toBody({ ...EMPTY, how: "prefix", prefix: "  " })).toEqual({ problem: "Write the start of the names." });
    expect(body({ ...EMPTY, how: "prefix", prefix: " Lore: " })).toMatchObject({ names: [], name_prefix: "Lore:" });
    expect(body({ ...EMPTY, how: "all", names: ["Lore"] })).toMatchObject({ names: [], name_prefix: null });
  });

  it("builds the condition only when it is not for everyone", () => {
    expect(body({ ...EMPTY, names: ["Lore"], blocks: [{ type: "finished" }] }).condition).toBeNull();
    expect(toBody({ ...EMPTY, names: ["Lore"], everyone: false })).toEqual({ problem: "Add at least one block to the condition." });
  });

  it("sends the rating only for a set rating, and the games only with Willpower", () => {
    expect(body({ ...EMPTY, names: ["Lore"], rating: 3 })).toMatchObject({ holds: "same", rating: null });
    expect(body({ ...EMPTY, names: ["Lore"], holds: "rating", rating: 3 })).toMatchObject({ holds: "rating", rating: 3 });
    expect(body({ ...EMPTY, names: ["Lore"], games: 4 })).toMatchObject({ willpower: 0, games: 0 });
    expect(toBody({ ...EMPTY, names: ["Lore"], willpower: 1, games: 0 })).toEqual({ problem: "Say after how many games the Willpower returns." });
  });
});

describe("draftOf", () => {
  const saved = (rule: Partial<TeacherRuleOut>): TeacherRuleOut => ({
    id: "r1",
    text: "",
    problem: null,
    splat: "vampire",
    category: "skills",
    names: [],
    name_prefix: null,
    condition: null,
    always: false,
    holds: "same",
    rating: null,
    actions: 0,
    willpower: 0,
    games: 0,
    ...rule,
  });

  it("gives back each example as it was built", () => {
    for (const { draft } of EXAMPLES) {
      expect(draftOf(saved(body(draft)))).toEqual(draft.how === "all" ? { ...draft, names: [] } : draft);
    }
  });

  it("reads a prefix, and a set rating", () => {
    expect(draftOf(saved({ name_prefix: "Lore", holds: "rating", rating: 2 }))).toMatchObject({ how: "prefix", prefix: "Lore", holds: "rating", rating: 2 });
  });

  it("cannot show a condition with no blocks for it", () => {
    expect(draftOf(saved({ condition: { npc: true } }))).toBeNull();
  });
});

describe("ruleAbout", () => {
  it("matches the category, then the names or the prefix", () => {
    expect(ruleAbout({ category: "lore_specializations", names: [], name_prefix: null }, "lore_specializations", "Sabbat")).toBe(true);
    expect(ruleAbout({ category: "lore_specializations", names: [], name_prefix: null }, "skills", "Lore")).toBe(false);
    expect(ruleAbout({ category: "skills", names: ["Drive"], name_prefix: null }, "skills", "Firearms")).toBe(false);
    expect(ruleAbout({ category: "skills", names: [], name_prefix: "Lore" }, "skills", "Lore")).toBe(true);
  });
});

describe("teachable", () => {
  it("offers kinds of trait bought in dots, but not merits and flaws", () => {
    const catalogue = {
      categories: [
        { key: "clan", rated: false, derived: false },
        { key: "skills", rated: true, derived: false },
        { key: "merits", rated: true, derived: false },
        { key: "health_levels", rated: true, derived: true },
      ],
      traits: [
        { category: "clan", name: "Brujah" },
        { category: "skills", name: "Lore" },
        { category: "merits", name: "Iron Will" },
        { category: "health_levels", name: "Healthy" },
      ],
    } as unknown as CatalogueOut;
    expect(teachable(catalogue).map((c) => c.key)).toEqual(["skills"]);
  });
});

it("says the teacher's Willpower in words", () => {
  expect(willpowerText(1, 2)).toBe("1 Willpower, back after 2 games");
  expect(willpowerText(2, 1)).toBe("2 Willpower, back after 1 game");
});
