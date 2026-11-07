import { describe, expect, it } from "vitest";
import type { KeywordChoiceOut } from "../../api/types";
import { baseCost, dropped, feedingFromAnswers, withKeyword } from "./keywords";

const kw = (key: string, fields: string[] = [], cost = 1): KeywordChoiceOut => ({
  key,
  name: key,
  explanation: "",
  fields,
  cost,
  retired: false,
  effect: key,
});
const feed = kw("feed", ["territory"]);
const patrol = kw("patrol", ["territory"]);
const learn = kw("learn", ["trait", "teacher"]);
const narrative = kw("narrative");
const observe = kw("observe", ["character"]);
const keywords = [feed, patrol, learn, narrative, observe];

describe("downtime keywords", () => {
  it("keeps the description's fields and drops what the new keyword doesn't ask for", () => {
    const fields = {
      keyword: "learn",
      learn: "Celerity 2",
      teacher: "Mira",
      aimed_at: ["a", "b"],
      project_id: "p",
    };
    expect(dropped(fields, narrative)).toEqual(["what to learn", "the teacher"]);
    expect(dropped(fields, learn)).toEqual([]);
    expect(withKeyword(fields, narrative)).toEqual({
      keyword: "narrative",
      aimed_at: ["a", "b"],
      project_id: "p",
    });
    // An Observe is aimed at one character.
    expect(withKeyword(fields, observe).aimed_at).toEqual(["a"]);
  });

  it("costs nothing more for something already being learned, or feeding in a territory", () => {
    expect(baseCost({ keyword: "learn", owed_action_id: "x" }, keywords)).toBe(0);
    expect(baseCost({ keyword: "learn" }, keywords)).toBe(1);
    expect(baseCost({ keyword: "feed", territory: "docks" }, keywords)).toBe(0);
    expect(baseCost({ keyword: "feed" }, keywords)).toBe(1);
    expect(baseCost(undefined, keywords)).toBe(1);
  });

  it("makes the Feeding section's actions and patrols from Feed and Patrol answers", () => {
    const answers = [
      { keyword: "feed", territory: "docks" },
      { keyword: "feed" },
      { keyword: "patrol", territory: "docks" },
      { keyword: "patrol", territory: "docks" },
    ];
    expect(feedingFromAnswers(answers, keywords)).toEqual({
      actions: 1,
      territory: "docks",
      patrols: [{ territory_id: "docks", actions: 2 }],
    });
    expect(feedingFromAnswers([{ keyword: "narrative" }], keywords)).toEqual({
      actions: null,
      territory: null,
      patrols: null,
    });
  });
});
