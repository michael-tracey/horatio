import { describe, expect, it } from "vitest";
import type { DerivedOut, EndingOut, PatronChoiceOut } from "../../api/types";
import { bySource, capText, endingText, findPatrons, outsiderText, patronLabel, suppressedText } from "./status";

const day = (d: string) => `day ${d}`;
const ending = (over: Partial<EndingOut>): EndingOut => ({
  text: "",
  not_before: null,
  games_left: 0,
  while_held: null,
  this_game: false,
  ...over,
});

describe("the fleeting cap", () => {
  it("says why it is not the usual, and nothing when it is", () => {
    expect(capText(["a lesser ban: 3", "Tainted Embrace: 1 less"])).toBe("Cap: a lesser ban: 3 · Tainted Embrace: 1 less");
    expect(capText([])).toBe("");
  });
  it("says how a character no sect has Accepted holds status", () => {
    expect(outsiderText({ outsider_sect: "Camarilla", outsider_through: "Emissary to the Camarilla" })).toBe(
      "Accepted by no sect. As Emissary to the Camarilla allows, it holds fleeting Camarilla status.",
    );
  });
});

describe("endingText", () => {
  it("says the games and the day, whichever is later", () => {
    expect(endingText(ending({ games_left: 2, not_before: "2026-11-26" }), day)).toBe(
      "Ends after 2 more games, and not before day 2026-11-26",
    );
    expect(endingText(ending({ games_left: 1 }), day)).toBe("Ends after 1 more game");
  });

  it("says what a status lasting while another is held waits on", () => {
    expect(endingText(ending({ while_held: "Warned", games_left: 2 }), day)).toBe(
      "Lasts while Warned is held; then ends after 2 more games",
    );
  });

  it("ends with the game it was given at", () => {
    expect(endingText(ending({ this_game: true, games_left: 1 }), day)).toBe("Ends with the game it was given at");
  });
});

describe("suppressedText", () => {
  it("says why, and when the fleeting status comes back", () => {
    expect(
      suppressedText({ text: "for defying a Commander", reason: "Defied the Prince", ending: ending({ games_left: 2, not_before: "2026-11-26" }) }, day),
    ).toBe("Fleeting status suppressed for defying a Commander (Defied the Prince): back after 2 more games, and not before day 2026-11-26.");
    expect(suppressedText({ text: "while it holds Vulgar", reason: "", ending: ending({ this_game: true, games_left: 1 }) }, day)).toBe(
      "Fleeting status suppressed while it holds Vulgar: back when the game ends.",
    );
  });
});

const derived = (name: string, source: string, kind: DerivedOut["kind"] = "title"): DerivedOut => ({
  name,
  type: "Abiding",
  source,
  kind,
  troupe_id: kind === "title" ? "t1" : null,
  troupe_name: kind === "title" ? "Court" : null,
  condition: "",
});

describe("bySource", () => {
  it("groups derived status by title, age and merit", () => {
    const groups = bySource([derived("Authority", "Prince"), derived("Commander", "Prince"), derived("Confirmed", "Elder", "social_age")]);
    expect(groups.map((g) => [g.source, g.status.map((s) => s.name)])).toEqual([
      ["Prince", ["Authority", "Commander"]],
      ["Elder", ["Confirmed"]],
    ]);
  });
});

const patron = (name: string, title = ""): PatronChoiceOut => ({ id: name, name, kind: "pc", title });

describe("patrons", () => {
  it("shows the title held", () => {
    expect(patronLabel(patron("Elena Varga", "Prince"))).toBe("Elena Varga (Prince)");
    expect(patronLabel(patron("Tomas Reyes"))).toBe("Tomas Reyes");
  });

  it("finds by name or title, names starting with it first", () => {
    const all = [patron("Ava Prince"), patron("Elena Varga", "Prince"), patron("Tomas Reyes")];
    expect(findPatrons(all, "prince").map((p) => p.name)).toEqual(["Ava Prince", "Elena Varga"]);
    expect(findPatrons(all, "tom").map((p) => p.name)).toEqual(["Tomas Reyes"]);
    expect(findPatrons(all, "")).toHaveLength(3);
  });
});
