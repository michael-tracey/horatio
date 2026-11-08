import { describe, expect, it } from "vitest";
import { banHint, sameClans, toggled } from "./StatusBanClans";

describe("status bans on clans", () => {
  it("compares lists of clans in any order", () => {
    expect(sameClans(["Ventrue", "Assamite"], ["Assamite", "Ventrue"])).toBe(true);
    expect(sameClans(["Ventrue"], ["Ventrue", "Brujah"])).toBe(false);
  });

  it("ticks a clan in order, and unticks it", () => {
    expect(toggled(["Assamite", "Ventrue"], "Gangrel", true)).toEqual(["Assamite", "Gangrel", "Ventrue"]);
    expect(toggled(["Assamite", "Gangrel"], "Gangrel", true)).toEqual(["Assamite", "Gangrel"]);
    expect(toggled(["Assamite", "Gangrel"], "Gangrel", false)).toEqual(["Assamite"]);
  });

  it("says who the ban falls on", () => {
    const ban = {
      key: "pillar_clans",
      sect: "Camarilla",
      label: "Pillar clans",
      level: "lesser",
      outside: true,
      page: "403",
      clans: [],
      book: [],
      applies_to: null,
      book_applies_to: "",
      presets: [],
    };
    expect(banHint(ban)).toBe("A Camarilla character of none of these clans is under a lesser status ban.");
    expect(banHint({ ...ban, sect: "Sabbat", outside: false, level: "greater" })).toBe("A Sabbat character of one of these clans is under a greater status ban.");
  });
});
