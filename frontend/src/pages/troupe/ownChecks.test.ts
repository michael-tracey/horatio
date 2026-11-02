import { describe, expect, it } from "vitest";
import type { OwnCheckOut } from "../../api/types";
import { BuildProblem, EMPTY, draftOf, fromCondition, newCondBlock, toBody, toCondition, type CondBlock } from "./ownChecks";

const has = (category: string, name: string, rating: number | null = null): CondBlock => ({ type: "has", category, name, rating });

/** The five examples from Land of the Sky's house rules, as blocks and as the server runs them. */
const EXAMPLES: [string, CondBlock[], Record<string, unknown>][] = [
  ["Pliable Blood only at creation", [{ type: "finished" }], { finished: true }],
  [
    "Daughters of Cacophony and Nagaraja no older than Generation 4",
    [
      {
        type: "any_of",
        blocks: [
          { type: "not", blocks: [{ type: "clan_family", names: ["Daughters of Cacophony", "Nagaraja"] }] },
          { type: "generation_lte", value: 4 },
        ],
      },
    ],
    { any_of: [{ not: { clan_family: ["Daughters of Cacophony", "Nagaraja"] } }, { generation: { lte: 4 } }] },
  ],
  [
    "Some clans need Alternate Identity 5",
    [
      {
        type: "any_of",
        blocks: [
          { type: "not", blocks: [{ type: "clan", names: ["Caitiff", "Giovanni", "Tremere: Telyav"] }] },
          has("backgrounds", "Alternate Identity", 5),
        ],
      },
    ],
    {
      any_of: [
        { not: { clan: ["Caitiff", "Giovanni", "Tremere: Telyav"] } },
        { has: { category: "backgrounds", name: "Alternate Identity", rating: 5 } },
      ],
    },
  ],
  [
    "One of each shared background",
    [
      { type: "copies", value: 2 },
      { type: "self", names: ["Allies", "Haven"] },
    ],
    { copies: { gte: 2 }, self: { names: ["Allies", "Haven"] } },
  ],
  [
    "Outside the Camarilla, Emissary to the Camarilla",
    [{ type: "any_of", blocks: [has("sect", "Camarilla"), has("merits", "Emissary to the Camarilla")] }],
    { any_of: [{ has: { category: "sect", name: "Camarilla" } }, { has: { category: "merits", name: "Emissary to the Camarilla" } }] },
  ],
];

describe("toCondition and fromCondition", () => {
  it.each(EXAMPLES)("builds %s and reads it back", (_, blocks, condition) => {
    expect(toCondition(blocks)).toEqual(condition);
    expect(fromCondition(condition)).toEqual(blocks);
  });

  it("puts two traits held side by side in has_all, and reads them back as two blocks", () => {
    const blocks = [has("merits", "Iron Will"), has("backgrounds", "Fame", 2)];
    const condition = toCondition(blocks);
    expect(condition).toEqual({
      has_all: [
        { category: "merits", name: "Iron Will" },
        { category: "backgrounds", name: "Fame", rating: 2 },
      ],
    });
    expect(fromCondition(condition)).toEqual(blocks);
  });

  it("puts Generation at least and at most in one table", () => {
    const blocks: CondBlock[] = [
      { type: "generation_gte", value: 2 },
      { type: "generation_lte", value: 4 },
    ];
    expect(toCondition(blocks)).toEqual({ generation: { gte: 2, lte: 4 } });
    expect(fromCondition({ generation: { gte: 2, lte: 4 } })).toEqual(blocks);
  });

  it("makes two Nots side by side neither of them", () => {
    const condition = toCondition([
      { type: "not", blocks: [{ type: "finished" }] },
      { type: "not", blocks: [has("merits", "Iron Will")] },
    ]);
    expect(condition).toEqual({ not: { any_of: [{ finished: true }, { has: { category: "merits", name: "Iron Will" } }] } });
  });

  it("keeps several blocks in one option of Any of as All of", () => {
    const blocks: CondBlock[] = [
      {
        type: "any_of",
        blocks: [{ type: "all_of", blocks: [{ type: "clan", names: ["Brujah"] }, { type: "finished" }] }, has("merits", "Iron Will")],
      },
    ];
    const condition = toCondition(blocks);
    expect(condition).toEqual({ any_of: [{ clan: ["Brujah"], finished: true }, { has: { category: "merits", name: "Iron Will" } }] });
    expect(fromCondition(condition)).toEqual(blocks);
  });

  it("reads creation not finished as Not creation finished", () => {
    expect(fromCondition({ finished: false })).toEqual([{ type: "not", blocks: [{ type: "finished" }] }]);
  });

  it.each<[string, CondBlock[], string]>([
    ["nothing", [], "Add at least one block to the condition."],
    ["a clan block with no clan", [newCondBlock("clan")], "Choose at least one clan."],
    ["a trait block with no trait", [newCondBlock("has")], "Choose the trait it holds."],
    ["an empty Not", [newCondBlock("not")], "Put a block inside “Not”."],
    ["Any of with one block", [{ type: "any_of", blocks: [{ type: "finished" }] }], "“Any of” needs at least two blocks."],
    ["the same block twice", [{ type: "finished" }, { type: "finished" }], "“Character creation is finished” is used twice side by side; put one of them under “Any of” or “Not”."],
    ["at least twice", [newCondBlock("generation_gte"), newCondBlock("generation_gte")], "“Generation at least…” is used twice side by side."],
  ])("says what is missing: %s", (_, blocks, message) => {
    expect(() => toCondition(blocks)).toThrow(new BuildProblem(message));
  });

  it("refuses a condition the form has no blocks for", () => {
    expect(() => fromCondition({ in_clan: true })).toThrow(BuildProblem);
    expect(() => fromCondition({ generation: { gt: 3 } })).toThrow(BuildProblem);
  });
});

describe("toBody and draftOf", () => {
  const saved = (over: Partial<OwnCheckOut>): OwnCheckOut => ({
    id: "c1",
    key: "house-check/c1",
    splat: "vampire",
    category: "merits",
    name: "Pliable Blood",
    name_prefix: null,
    kind: null,
    mode: "forbids",
    condition: { finished: true },
    strength: "refuse",
    message: "Pliable Blood can only be taken at character creation.",
    step: null,
    text: "Pliable Blood: refused once creation is finished.",
    problem: null,
    breaking: [],
    ...over,
  });

  it("turns a draft into what the server takes, by how the subject is picked", () => {
    const draft = { ...EMPTY, category: "merits", how: "kind" as const, value: "Clan", blocks: [{ type: "finished" as const }], message: "No." };
    expect(toBody(draft)).toEqual({
      body: {
        splat: "vampire",
        category: "merits",
        name: null,
        name_prefix: null,
        kind: "Clan",
        mode: "forbids",
        condition: { finished: true },
        strength: "refuse",
        message: "No.",
        step: null,
      },
    });
  });

  it("names a step only for a check needed to finish creation", () => {
    const draft = { ...EMPTY, how: "all" as const, blocks: [{ type: "finished" as const }], step: "backgrounds" };
    expect("body" in toBody(draft) && toBody(draft)).toMatchObject({ body: { step: null } });
    expect(toBody({ ...draft, strength: "complete" })).toMatchObject({ body: { step: "backgrounds" } });
  });

  it("says what is missing before a body can be made", () => {
    expect(toBody({ ...EMPTY, blocks: [{ type: "finished" }] })).toEqual({ problem: "Choose the trait it is about." });
    expect(toBody({ ...EMPTY, value: "Iron Will" })).toEqual({ problem: "Add at least one block to the condition." });
  });

  it("reads a saved check back into the form", () => {
    expect(draftOf(saved({}))).toEqual({
      splat: "vampire",
      category: "merits",
      how: "trait",
      value: "Pliable Blood",
      mode: "forbids",
      blocks: [{ type: "finished" }],
      strength: "refuse",
      message: "Pliable Blood can only be taken at character creation.",
      step: "",
    });
    expect(draftOf(saved({ name: null, category: "clan" }))?.how).toBe("all");
    expect(draftOf(saved({ name: null, name_prefix: "Bloodline:" }))).toMatchObject({ how: "prefix", value: "Bloodline:" });
    expect(draftOf(saved({ condition: { npc: true } }))).toBeNull();
  });
});
