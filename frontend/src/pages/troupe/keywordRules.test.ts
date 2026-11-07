import { describe, expect, it } from "vitest";
import type { KeywordsOut, TroupeKeywordOut } from "../../api/types";
import { keywordFields, keywordKinds, moved } from "./keywordRules";

const data = {
  keywords: [],
  steps: [],
  fields: [
    { key: "territory", label: "A feeding territory" },
    { key: "target", label: "Who or what it is aimed at: a character, or something else in words" },
  ],
  action_kinds: { general: "Downtime action" },
  ages: [],
} as KeywordsOut;
const keyword = (over: Partial<TroupeKeywordOut>) =>
  ({
    key: "x",
    name: "X",
    explanation: "",
    fields: [],
    action_kinds: ["general"],
    computers_only: false,
    science: false,
    cost: 1,
    required_for: [],
    step: 5,
    position: 0,
    retired: false,
    effect: null,
    text: "",
    ...over,
  }) as TroupeKeywordOut;

describe("keyword rules", () => {
  it("says what a keyword asks for and is spent from", () => {
    expect(keywordFields(keyword({ fields: ["territory", "target"] }), data)).toBe("A feeding territory, Who or what it is aimed at");
    expect(keywordKinds(keyword({}), data)).toBe("Downtime action");
    expect(keywordKinds(keyword({ computers_only: true }), data)).toBe("The Computer skill's action");
    expect(keywordKinds(keyword({ action_kinds: [], effect: "quest" }), data)).toBe("The form's Quest action");
  });

  it("moves a keyword up or down, and no further than the ends", () => {
    expect(moved(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    expect(moved(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(moved(["a", "b", "c"], 0, -1)).toEqual(["a", "b", "c"]);
  });
});
