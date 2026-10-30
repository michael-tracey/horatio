import { describe, expect, it } from "vitest";
import type { LocationOut } from "../../api/types";
import { controlText, countText, filtered, NO_FILTERS, parseSuggestions, qualitiesText, suggestionLines, suggestionText, typeText } from "./locations";

function location(change: Partial<LocationOut>): LocationOut {
  return {
    id: "1",
    troupe_id: "t",
    name: "Grove Arcade",
    parent: null,
    kind: "prestige",
    rating: 5,
    qualities: [],
    quality_count: 0,
    most_qualities: 10,
    negatives: [],
    control: "none",
    controller: null,
    joint: null,
    heir: null,
    influence_type: null,
    influence_area: "",
    address: "1 Page Ave",
    web_address: "",
    map_link: "",
    feeding_block: "",
    locked: false,
    haven_of: null,
    haven_advantages: [],
    elysium_since: null,
    elysium_qualities: null,
    notes: "",
    subsidiaries: [],
    not_counted: null,
    updated_at: "2026-10-30T00:00:00Z",
    ...change,
  };
}

const held = (name: string, detail = "") => ({ name, detail, kind: "standard" as const, known: true, counts: true, house: false, free_here: "" });

describe("locations", () => {
  it("says its type, control and qualities in a few words", () => {
    expect(typeText({ kind: "prestige", rating: 5 })).toBe("Prestige 5");
    expect(controlText({ control: "uncontrollable", controller: null, joint: null })).toBe("Uncontrollable");
    expect(controlText({ control: "none", controller: null, joint: null })).toBe("Uncontrolled");
    expect(controlText({ control: "character", controller: { id: "a", name: "Agnes" }, joint: { id: null, name: "Doris" } })).toBe("Agnes and Doris");
    expect(qualitiesText([held("Profitable"), held("Size"), held("Profitable"), held("Laboratory", "Chemistry")])).toBe(
      "Profitable ×2, Size, Laboratory (Chemistry)",
    );
    expect(countText({ kind: "prestige", quality_count: 10, most_qualities: 10 })).toBe("10 of 10 qualities");
    expect(countText({ kind: "haven", quality_count: 0, most_qualities: 0 })).toBe("");
  });

  it("filters by search, controller, quality, lock and negatives", () => {
    const grove = location({ qualities: [held("Fancy")], control: "character", controller: { id: "a", name: "Agnes" } });
    const rack = location({
      id: "2",
      name: "The Rack bar",
      address: "Lexington",
      locked: true,
      negatives: [{ name: "Compromised", level: 1, secret: true, by: "hunters", effect: "" }],
    });
    const all = [grove, rack];
    expect(filtered(all, { ...NO_FILTERS, query: "lexing" })).toEqual([rack]);
    expect(filtered(all, { ...NO_FILTERS, controller: "c:a" })).toEqual([grove]);
    expect(filtered(all, { ...NO_FILTERS, controller: "none" })).toEqual([rack]);
    expect(filtered(all, { ...NO_FILTERS, quality: "Fancy" })).toEqual([grove]);
    expect(filtered(all, { ...NO_FILTERS, locked: "open" })).toEqual([grove]);
    expect(filtered(all, { ...NO_FILTERS, negatives: "secret" })).toEqual([rack]);
    expect(filtered(all, { ...NO_FILTERS, negatives: "none" })).toEqual([grove]);
  });

  it("writes and reads suggested requirements as the troupe's sheet does", () => {
    expect(suggestionText({ trait: "Crafts", levels: [2, 3, 4] })).toBe("Crafts [2,3,4]");
    expect(suggestionText({ trait: "Resources", levels: [4, 5], expend: true })).toBe("expend Resources [4,5]");
    expect(suggestionText({ trait: "Academics", levels: [4, 5], alternative: "an Art specialisation" })).toBe("Academics [4,5], or an Art specialisation");
    expect(suggestionText({ power: "Presence: Entrancement" })).toBe("Presence: Entrancement");
    expect(suggestionText({ traits: ["Contacts", "Allies"], detail: "Arts" })).toBe("Contacts or Allies (Arts)");
    const typed = "Crafts [2, 3, 4]\nexpend Resources [5,4]\n\nA good ladder";
    expect(parseSuggestions(typed)).toEqual([
      { trait: "Crafts", levels: [2, 3, 4] },
      { trait: "Resources", levels: [4, 5], expend: true },
      { text: "A good ladder" },
    ]);
    expect(suggestionLines(parseSuggestions(typed))).toBe("Crafts [2,3,4]\nexpend Resources [4,5]\nA good ladder");
  });
});
