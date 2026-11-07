import { describe, expect, it } from "vitest";
import { unmatchedLines, type ReportCharacter } from "./yorickImport";

function character(name: string, sources: string[]): ReportCharacter {
  return {
    legacy_id: name,
    name,
    label: "",
    outcome: "made",
    skipped_because: "",
    character_id: null,
    matches: [],
    choice: null,
    unmatched: sources.map((source) => {
      const [heading = "", text = ""] = source.split(": ");
      return { heading, text, reason: "no such merit", source, part: "names", category: "merits", key: text };
    }),
    refused: [],
    revalued: [],
    problems: [],
    unpriced: [],
    left_out: [],
    split: [],
    traits: 10,
    xp: 0,
    portrait: "none",
  };
}

describe("unmatchedLines", () => {
  it("lists each printed line once, the most printed first, with lines left for staff apart", () => {
    const { waiting, handed } = unmatchedLines(
      [character("Agnes", ["Merits: Arcane", "Merits: Bold"]), character("Thad", ["Merits: Bold", "Flaws: Odd"]), character("Mary", ["Merits: Bold"])],
      ["Flaws: Odd"],
    );

    expect(waiting.map((l) => [l.source, l.characters])).toEqual([
      ["Merits: Bold", ["Agnes", "Thad", "Mary"]],
      ["Merits: Arcane", ["Agnes"]],
    ]);
    expect(handed.map((l) => l.source)).toEqual(["Flaws: Odd"]);
  });
});
