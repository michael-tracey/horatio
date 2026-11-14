import { describe, expect, it } from "vitest";
import { toggled, touchedText } from "./motifTags";

const scene = { id: "s", name: "Ballroom" };
const quest = { id: "q", name: "Journal", status: "active" };

describe("touchedText", () => {
  it("counts the scenes and quests a theme or mood touches", () => {
    expect(touchedText({ scenes: [scene, scene], quests: [quest] })).toBe("2 scenes, 1 quest");
    expect(touchedText({ scenes: [], quests: [quest, quest] })).toBe("2 quests");
    expect(touchedText({ scenes: [scene], quests: [] })).toBe("1 scene");
  });

  it("says when nothing touches it", () => {
    expect(touchedText({ scenes: [], quests: [] })).toBe("Not touched yet");
  });
});

describe("toggled", () => {
  it("puts a tag on or takes it off", () => {
    expect(toggled(["a"], "b")).toEqual(["a", "b"]);
    expect(toggled(["a", "b"], "a")).toEqual(["b"]);
  });
});
