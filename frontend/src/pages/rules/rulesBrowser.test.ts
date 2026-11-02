import { describe, expect, it } from "vitest";
import type { RulesBrowserOut, TraitOut } from "../../api/types";
import { applyFilters, entries, generalChecks, ratingChoices, rulesLink, sectionCounts, shownChecks, type Filters } from "./rulesBrowser";

const trait = (category: string, name: string, more: Partial<TraitOut> = {}) =>
  ({
    category,
    name,
    description: null,
    page_reference: null,
    fixed_rating: null,
    house_rule: null,
    in_clan: null,
    attribute: null,
    requirement: null,
    kind: null,
    house: null,
    ...more,
  }) as TraitOut;

const data = (more: Partial<RulesBrowserOut> = {}): RulesBrowserOut => ({
  catalogue: {
    splat: "vampire",
    name: "MET: VtM",
    categories: [],
    traits: [
      trait("merits", "Absent Sway", { fixed_rating: 3, requirement: "Toreador", kind: "Clan", description: "Art that stirs a chosen emotion." }),
      trait("merits", "Calm Heart", { fixed_rating: 1, kind: "General" }),
      trait("merits", "Volgirre Grace", { fixed_rating: 2, requirement: "Toreador: Volgirre" }),
      trait("disciplines", "Presence", { description: "Supernatural charisma." }),
      trait("disciplines", "Auspex"),
      trait("elder_disciplines", "Presence: Love"),
      trait("clan", "Toreador", { in_clan: ["Auspex", "Celerity", "Presence"] }),
      trait("clan", "Toreador: Volgirre", { in_clan: ["Auspex"] }),
      trait("clan", "Brujah", { in_clan: ["Celerity", "Potence", "Presence"] }),
      trait("rituals", "Thaumaturgy: Ward", { fixed_rating: 2 }),
      trait("archetype", "Architect"),
    ],
  },
  troupe_name: null,
  prices: [],
  requirements: [],
  not_allowed: [],
  powers: [
    { discipline: "Presence", level: 1, name: "Awe", note: "Draw every eye in the room." },
    { discipline: "Presence", level: 5, name: "Majesty", note: "For an hour, no one can act against you without spending Willpower." },
  ],
  rarities: [{ clan: "Toreador", text: "Common", page: "403", house: false }],
  ...more,
});

const none: Filters = { section: "", query: "", clan: "", rating: null, barred: false };
const names = (found: { name: string }[]) => found.map((e) => e.name);

describe("entries", () => {
  it("lists what the browser shows, by section, each discipline followed by its powers", () => {
    expect(names(entries(data()))).toEqual([
      "Absent Sway",
      "Calm Heart",
      "Volgirre Grace",
      "Auspex",
      "Presence",
      "Awe",
      "Majesty",
      "Presence: Love",
      "Thaumaturgy: Ward",
      "Brujah",
      "Toreador",
      "Toreador: Volgirre",
    ]);
  });

  it("says a merit's points, a ritual's level and a power's discipline and dot", () => {
    const by = new Map(entries(data()).map((e) => [e.name, e]));
    expect(by.get("Absent Sway")?.rating).toBe("3 points");
    expect(by.get("Calm Heart")?.rating).toBe("1 point");
    expect(by.get("Thaumaturgy: Ward")?.rating).toBe("Level 2");
    expect(by.get("Majesty")?.rating).toBe("Presence 5");
    expect(by.get("Presence")?.rating).toBeNull();
  });

  it("gives a bloodline its clan's rarity", () => {
    const by = new Map(entries(data()).map((e) => [e.name, e]));
    expect(by.get("Toreador: Volgirre")?.rarity?.text).toBe("Common");
  });
});

describe("applyFilters", () => {
  const all = entries(data());

  it("finds a power by its name and by a word in its summary", () => {
    expect(names(applyFilters(all, { ...none, query: "majesty" }))).toEqual(["Majesty"]);
    expect(names(applyFilters(all, { ...none, query: "WILLPOWER hour" }))).toEqual(["Majesty"]);
  });

  it("finds the merits a clan needs, with its bloodlines'", () => {
    expect(names(applyFilters(all, { ...none, section: "merits", query: "toreador" }))).toEqual(["Absent Sway", "Volgirre Grace"]);
  });

  it("narrows to a clan: what it is for, and its in-clan disciplines and their powers", () => {
    expect(names(applyFilters(all, { ...none, clan: "Toreador" }))).toEqual([
      "Absent Sway",
      "Volgirre Grace",
      "Auspex",
      "Presence",
      "Awe",
      "Majesty",
      "Presence: Love",
      "Toreador",
      "Toreador: Volgirre",
    ]);
  });

  it("narrows to points or a level", () => {
    expect(names(applyFilters(all, { ...none, section: "merits", rating: 3 }))).toEqual(["Absent Sway"]);
    expect(names(applyFilters(all, { ...none, section: "disciplines", rating: 5 }))).toEqual(["Majesty"]);
  });

  it("hides what the troupe does not allow, unless asked to show it", () => {
    const barred = entries(data({ not_allowed: [{ category: "merits", name: "Calm Heart", text: null }] }));
    expect(names(applyFilters(barred, { ...none, section: "merits" }))).toEqual(["Absent Sway", "Volgirre Grace"]);
    expect(names(applyFilters(barred, { ...none, section: "merits", barred: true }))).toContain("Calm Heart");
  });

  it("treats a trait the troupe bans as not allowed, with its reason", () => {
    const base = data();
    const traits = base.catalogue.traits.map((t) => (t.name === "Calm Heart" ? { ...t, changed: { banned: true, ban_reason: "Not here." } } : t));
    const found = entries({ ...base, catalogue: { ...base.catalogue, traits } });
    expect(names(applyFilters(found, { ...none, section: "merits" }))).toEqual(["Absent Sway", "Volgirre Grace"]);
    const calm = found.find((e) => e.name === "Calm Heart")!;
    expect([calm.banned, calm.barred?.text]).toEqual([true, "Not here."]);
  });
});

describe("sectionCounts and ratingChoices", () => {
  const all = entries(data());

  it("counts what each section holds under the other filters", () => {
    const counts = sectionCounts(all, { ...none, section: "merits", query: "presence" });
    expect(Object.fromEntries(counts)).toEqual({ disciplines: 4 });
  });

  it("offers the ratings a section has", () => {
    expect(ratingChoices(all, "merits")).toEqual([1, 2, 3]);
    expect(ratingChoices(all, "skills")).toEqual([]);
  });
});

describe("checks", () => {
  const read = data({
    requirements: [
      { key: "merits/Absent Sway/requirement", category: "merits", trait: "Absent Sway", prefix: null, message: "Absent Sway is only for Toreador.", page: "243", strength: "refuse", house: null },
      { key: "merits/Absent Sway/1", category: "merits", trait: "Absent Sway", prefix: null, message: "Absent Sway needs Presence 1.", page: null, strength: "refuse", house: null },
      { key: "merits/*/1", category: "merits", trait: null, prefix: null, message: "A merit can be taken only once.", page: "236", strength: "refuse", house: null },
    ],
  });

  it("leaves out a clan-only check the clan beside the name already says", () => {
    const sway = entries(read).find((e) => e.name === "Absent Sway")!;
    expect(shownChecks(sway).map((c) => c.message)).toEqual(["Absent Sway needs Presence 1."]);
  });

  it("keeps one the troupe changed", () => {
    const changed = data({ requirements: read.requirements.map((r) => ({ ...r, house: "off" })) });
    const sway = entries(changed).find((e) => e.name === "Absent Sway")!;
    expect(shownChecks(sway)).toHaveLength(2);
  });

  it("puts a whole category's checks under its heading", () => {
    expect(generalChecks(read, "merits").map((c) => c.message)).toEqual(["A merit can be taken only once."]);
  });
});

describe("rulesLink", () => {
  it("opens the browser on the first category it shows, as played in the troupe", () => {
    expect(rulesLink(["focus_physicals", "merits", "flaws"], "t-1")).toBe("/rules?category=merits&troupe=t-1");
    expect(rulesLink(["elder_disciplines"], null, "ghoul")).toBe("/rules?category=disciplines&splat=ghoul");
    expect(rulesLink(["health_levels"])).toBeNull();
  });
});
