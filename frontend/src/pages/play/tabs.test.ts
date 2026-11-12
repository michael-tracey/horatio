import { describe, expect, it } from "vitest";
import { openingChoices, openingTab, shownTabs, tabNames, TABS, tabsOn, usesPlayView } from "./tabs";

const EVERY = TABS.map((t) => t.key);

describe("a troupe's Play View tabs (#673)", () => {
  it("has every tab on by default", () => {
    expect(tabsOn([])).toEqual(["sheet", "tracker", "pools", "status", "equipment", "throws"]);
    expect(usesPlayView({ play_tabs_off: [] })).toBe(true);
  });

  it("leaves out the tabs switched off, and uses no Play View with every one off", () => {
    expect(tabsOn(["pools", "status"])).toEqual(["sheet", "tracker", "equipment", "throws"]);
    expect(usesPlayView({ play_tabs_off: ["sheet", "tracker", "pools", "status"] })).toBe(true);
    expect(usesPlayView({ play_tabs_off: EVERY })).toBe(false);
  });

  it("shows a character the tabs it has, and Status only with sect status", () => {
    expect(shownTabs(EVERY, true)).toEqual(EVERY);
    expect(shownTabs(EVERY, false)).toEqual(["sheet", "tracker", "pools", "equipment", "throws"]);
    expect(shownTabs(["sheet", "pools"], true)).toEqual(["sheet", "pools"]);
  });

  it("opens on the tab a link asks for, else the person's choice, else the first tab on", () => {
    expect(openingTab("pools", "tracker", EVERY)).toBe("pools");
    expect(openingTab(null, "sheet", EVERY)).toBe("sheet");
    // A link to a tab switched off, and a choice switched off.
    expect(openingTab("pools", "tracker", ["sheet", "equipment"])).toBe("sheet");
    expect(openingTab("nonsense", "pools", ["tracker", "equipment"])).toBe("tracker");
    expect(openingTab(null, "tracker", [])).toBeUndefined();
  });

  it("names the tabs in their order", () => {
    expect(tabNames(["pools", "sheet"])).toBe("Sheet and Pools");
    expect(tabNames(["equipment", "sheet", "tracker"])).toBe("Sheet, Tracker and Equipment");
    expect(tabNames(["status"])).toBe("Status");
  });
});

describe("Settings › the Play View opens on (#673)", () => {
  const choices = ["tracker", "sheet", "pools"] as const;
  const court = { name: "Night Court", play_tabs_off: ["pools" as const] };
  const owls = { name: "Court of Owls", play_tabs_off: [] };
  const sheetsOnly = { name: "Paper Club", play_tabs_off: EVERY };

  it("offers every choice with no troupe, or troupes with every tab on", () => {
    expect(openingChoices(choices, [])).toEqual({ offered: ["tracker", "sheet", "pools"], off: [] });
    expect(openingChoices(choices, [owls]).offered).toEqual(["tracker", "sheet", "pools"]);
  });

  it("offers a tab at least one troupe has on, and says which troupe switched it off", () => {
    expect(openingChoices(choices, [court])).toEqual({ offered: ["tracker", "sheet"], off: [{ tab: "pools", troupes: ["Night Court"] }] });
    expect(openingChoices(choices, [court, owls])).toEqual({ offered: ["tracker", "sheet", "pools"], off: [{ tab: "pools", troupes: ["Night Court"] }] });
  });

  it("leaves out a troupe that doesn't use the Play View", () => {
    expect(openingChoices(choices, [court, sheetsOnly])).toEqual({ offered: ["tracker", "sheet"], off: [{ tab: "pools", troupes: ["Night Court"] }] });
    expect(openingChoices(choices, [sheetsOnly]).offered).toEqual(["tracker", "sheet", "pools"]);
  });
});
