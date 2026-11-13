import { describe, expect, it } from "vitest";
import { characterTabGroups, questsView, repeatedLabels, type TabsFor } from "./characterTabs";

const none: TabsFor = {
  base: "/characters/c1",
  mine: false,
  creating: false,
  staffQuests: false,
  questsOn: false,
  influence: false,
  keepsProjects: false,
  shared: false,
  backstory: false,
  due: 0,
  newResults: 0,
};

const flags = ["mine", "creating", "staffQuests", "questsOn", "influence", "keepsProjects", "shared", "backstory"] as const;

/** Every combination of the flags. */
function everyCase(): TabsFor[] {
  return Array.from({ length: 1 << flags.length }, (_, n) => {
    const t = { ...none };
    flags.forEach((f, i) => (t[f] = !!(n & (1 << i))));
    return t;
  });
}

const labels = (t: TabsFor) => characterTabGroups(t).flatMap((g) => g.tabs.map((tab) => tab.label));

describe("characterTabGroups", () => {
  it("never shows two tabs with one label", () => {
    for (const t of everyCase()) expect(repeatedLabels(characterTabGroups(t)), JSON.stringify(t)).toEqual([]);
  });

  it("shows one Quests tab to a storyteller looking at their own character (#788)", () => {
    const t = { ...none, mine: true, staffQuests: true, questsOn: true };
    expect(labels(t).filter((l) => l === "Quests")).toHaveLength(1);
    expect(questsView(t)).toBe("player");
  });

  it("shows the player's quests after Results, and the staff's after Projects", () => {
    const between = (t: TabsFor) => characterTabGroups(t).find((g) => g.label === "Between games")!.tabs.map((tab) => tab.label);
    expect(between({ ...none, mine: true, questsOn: true, influence: true })).toEqual(["Downtime", "Results", "Quests", "Influence"]);
    expect(between({ ...none, staffQuests: true, questsOn: true, influence: true, keepsProjects: true })).toEqual(["Influence", "Projects", "Quests"]);
  });

  it("hides Quests while its troupes don't run them, and while its player is creating it", () => {
    expect(labels({ ...none, mine: true, staffQuests: true })).not.toContain("Quests");
    expect(labels({ ...none, mine: true, creating: true, questsOn: true })).not.toContain("Quests");
    expect(labels({ ...none, questsOn: true })).not.toContain("Quests");
  });
});

describe("repeatedLabels", () => {
  it("names a label two tabs carry, even in different groups", () => {
    expect(
      repeatedLabels([
        { label: "A", tabs: [{ to: "/a", label: "Quests" }] },
        { label: "B", tabs: [{ to: "/b", label: "Quests" }, { to: "/c", label: "Log" }] },
      ]),
    ).toEqual(["Quests"]);
  });
});
