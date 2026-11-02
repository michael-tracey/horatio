import { describe, expect, it } from "vitest";
import type { CategoryOut, TraitOut } from "../../api/types";
import { bookTraits, changeSummary, findTraits } from "./bookTraits";

const category = (key: string, name: string, derived = false) => ({ key, name, derived }) as CategoryOut;
const trait = (cat: string, name: string, more: Partial<TraitOut> = {}) =>
  ({ category: cat, name, description: null, house: null, changed: null, ...more }) as TraitOut;

const CATEGORIES = [category("clan", "Clan"), category("health_levels", "Health Levels", true), category("merits", "Merits")];
const TRAITS = [
  trait("merits", "Lucky", { description: "Downgrade an exceptional success." }),
  trait("merits", "Acute Sense"),
  trait("merits", "Child of the Crossroads", { house: { label: "House merit" } as TraitOut["house"] }),
  trait("health_levels", "Healthy"),
  trait("clan", "Brujah"),
];

describe("bookTraits", () => {
  it("leaves out house merits and derived categories, in the catalogue's order", () => {
    expect(bookTraits(TRAITS, CATEGORIES).map((t) => t.name)).toEqual(["Brujah", "Acute Sense", "Lucky"]);
  });
});

describe("findTraits", () => {
  const all = bookTraits(TRAITS, CATEGORIES);

  it("finds every word in the name or description, in one category or any", () => {
    expect(findTraits(all, "exceptional", "").map((t) => t.name)).toEqual(["Lucky"]);
    expect(findTraits(all, "", "clan").map((t) => t.name)).toEqual(["Brujah"]);
    expect(findTraits(all, "u", "merits").map((t) => t.name)).toEqual(["Acute Sense", "Lucky"]);
  });

  it("puts the troupe's changed traits first", () => {
    const changed = all.map((t) => (t.name === "Lucky" ? { ...t, changed: { banned: true, ban_reason: "", wording: "", wording_mode: "added" as const } } : t));
    expect(findTraits(changed, "u", "merits").map((t) => t.name)).toEqual(["Lucky", "Acute Sense"]);
  });
});

describe("changeSummary", () => {
  it("says a ban, with its reason", () => {
    expect(changeSummary({ banned: true, ban_reason: "Too swingy" })).toEqual(["Banned: Too swingy"]);
    expect(changeSummary({ banned: true, ban_reason: "" })).toEqual(["Banned"]);
    expect(changeSummary({ banned: false, ban_reason: "" })).toEqual([]);
  });

  it("says the troupe's wording, and how it reads beside the book's", () => {
    expect(changeSummary({ banned: false, ban_reason: "", wording: "One target.", wording_mode: "added" })).toEqual(["Own wording, added to the book's"]);
    expect(changeSummary({ banned: true, ban_reason: "", wording: "One target.", wording_mode: "replaces" })).toEqual([
      "Banned",
      "Own wording, in place of the book's",
    ]);
  });
});
