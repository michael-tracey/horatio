import { describe, expect, it } from "vitest";
import type { WhosWhoEntry, WhosWhoOut } from "../../api/types";
import { clanText, filterChoices, matches, sections } from "./whosWho";

function entry(id: string, name: string, clan: string | null, more: Partial<WhosWhoEntry> = {}): WhosWhoEntry {
  return {
    character_id: id,
    name,
    kind: "pc",
    picture: null,
    clan,
    social_age: "Neonate",
    sect: "Camarilla",
    player_id: null,
    player_name: null,
    titles: [],
    visible: [],
    bans: [],
    negative: [],
    visiting: false,
    visiting_from: null,
    pronouns: null,
    player_pronouns: null,
    represented_by: null,
    left_reason: null,
    ...more,
  };
}

const DATA: WhosWhoOut = {
  troupe_id: "t",
  troupe_name: "Court of Ash",
  entries: [
    entry("a", "Ada", "Brujah", { player_name: "Maria Lopez" }),
    entry("b", "Bruno", "Brujah: True Brujah", { titles: ["Primogen"] }),
    entry("g", "Gwen", "Gangrel", { sect: "Anarch" }),
    entry("v", "Varga", "Ventrue", { titles: ["Prince", "Primogen"] }),
  ],
  court: ["v", "b"],
  clans: [
    { clan: "Brujah", character_ids: ["a", "b"] },
    { clan: "Ventrue", character_ids: ["v"] },
  ],
  other: ["g"],
  departed: [],
  seated: ["Brujah", "Ventrue"],
  shows_negative: false,
};

const shown = (data: WhosWhoOut, filter = { query: "", clan: "", sect: "" }) => sections(data, filter).map((s) => [s.title, s.entries.map((e) => e.name)]);

describe("sections", () => {
  it("lists the court, each seated clan and Other, leaving out what is empty", () => {
    expect(shown(DATA)).toEqual([
      ["Court", ["Varga", "Bruno"]],
      ["Brujah", ["Ada", "Bruno"]],
      ["Ventrue", ["Varga"]],
      ["Other", ["Gwen"]],
    ]);
  });

  it("finds a character by its player's name or a title, in every section it is in", () => {
    expect(shown(DATA, { query: "lopez", clan: "", sect: "" })).toEqual([["Brujah", ["Ada"]]]);
    expect(shown(DATA, { query: "primogen", clan: "", sect: "" })).toEqual([
      ["Court", ["Varga", "Bruno"]],
      ["Brujah", ["Bruno"]],
      ["Ventrue", ["Varga"]],
    ]);
  });

  it("filters by clan, bloodlines with it, and by sect", () => {
    expect(shown(DATA, { query: "", clan: "Brujah", sect: "" })).toEqual([
      ["Court", ["Bruno"]],
      ["Brujah", ["Ada", "Bruno"]],
    ]);
    expect(shown(DATA, { query: "", clan: "", sect: "Anarch" })).toEqual([["Other", ["Gwen"]]]);
  });
});

describe("matches", () => {
  it("matches anything when the search is empty", () => {
    expect(matches(DATA.entries[0]!, "  ")).toBe(true);
  });
});

describe("clanText", () => {
  it("puts a bloodline after its clan", () => {
    expect(clanText("Brujah: True Brujah")).toBe("Brujah (True Brujah)");
    expect(clanText("Ventrue")).toBe("Ventrue");
    expect(clanText(null)).toBe("No clan yet");
  });
});

describe("filterChoices", () => {
  it("offers each clan family and sect once", () => {
    expect(filterChoices(DATA)).toEqual({ clans: ["Brujah", "Gangrel", "Ventrue"], sects: ["Anarch", "Camarilla"] });
  });
});
