import { describe, expect, it } from "vitest";
import { repeatedLabels } from "../character/characterTabs";
import { abilities } from "./roles";
import { troupeTabGroups, type TroupeTabsTroupe } from "./troupeTabs";

// Every optional part switched on, so each role's whole set shows.
const troupe: TroupeTabsTroupe = {
  id: "t1",
  archived: false,
  whos_who: true,
  nominations: true,
  player_nominations: true,
  court_history_players: true,
  chronicle_players: true,
  blood_bonds: "staff",
  boons: true,
  quests_enabled: true,
};

const roles = ["lead_storyteller", "storyteller", "assistant_storyteller", "narrator", null] as const;
const flags = ["archived", "whos_who", "nominations", "player_nominations", "court_history_players", "chronicle_players", "boons", "quests_enabled"] as const;

/** Every combination of the troupe's switches, with blood bonds off and on. */
function everyTroupe(): TroupeTabsTroupe[] {
  return Array.from({ length: 1 << (flags.length + 1) }, (_, n) => {
    const t: TroupeTabsTroupe = { ...troupe, blood_bonds: n & (1 << flags.length) ? "staff" : "off" };
    flags.forEach((f, i) => (t[f] = !!(n & (1 << i))));
    return t;
  });
}

/** Each shown group with its tabs' labels. */
function layout(can: ReturnType<typeof abilities>, t: TroupeTabsTroupe = troupe) {
  return Object.fromEntries(
    troupeTabGroups(t, can)
      .filter((g) => g.tabs.length > 0)
      .map((g) => [g.label, g.tabs.map((tab) => tab.label)]),
  );
}

const storytellerLayout = {
  Troupe: ["Overview", "The setting", "Who's Who", "News", "Announcements", "Nominations", "Chronicle", "Staff"],
  Characters: ["Approvals", "Roster", "Players", "Lines and veils", "Equipment", "Shared backgrounds"],
  "Game night": ["At game", "Scenes ↗", "Award XP"],
  Court: ["Titles", "Court over time", "Boons", "Bonds", "Web of obligation"],
  "Between games": ["Downtimes", "My work", "Fill tables", "Influence log", "Locations", "Quests"],
  "Setting up": ["Settings", "House rules", "Specialisations", "Connectors", "Export and import"],
};

describe("troupeTabGroups (#779, #1048)", () => {
  it("groups a lead storyteller's tabs by what staff are doing: 33 tabs in six groups", () => {
    expect(Object.values(storytellerLayout).flat()).toHaveLength(33);
    expect(layout(abilities("lead_storyteller", false))).toEqual(storytellerLayout);
  });

  it("never shows two tabs with one label, nor a tab named as its group (#905)", () => {
    for (const t of everyTroupe()) {
      for (const role of roles) {
        for (const custodian of [false, true]) {
          const groups = troupeTabGroups(t, abilities(role, custodian));
          const why = JSON.stringify({ role, custodian, ...t });
          expect(repeatedLabels(groups), why).toEqual([]);
          expect(groups.flatMap((g) => g.tabs.filter((tab) => tab.label === g.label).map((tab) => `${g.label} › ${tab.label}`)), why).toEqual([]);
        }
      }
    }
  });

  it("gives a storyteller and an assistant storyteller the same groups as the lead", () => {
    expect(layout(abilities("storyteller", false))).toEqual(storytellerLayout);
    expect(layout(abilities("assistant_storyteller", false))).toEqual(storytellerLayout);
  });

  it("gives a narrator the troupe, lines and veils, and their downtime work", () => {
    expect(layout(abilities("narrator", false))).toEqual({
      Troupe: ["Overview", "The setting", "Who's Who", "News", "Announcements", "Nominations", "Chronicle", "House rules", "Staff"],
      Characters: ["Lines and veils"],
      Court: ["Court over time"],
      "Between games": ["My work", "Fill tables", "Quests"],
    });
  });

  it("puts the chronicle under Troupe and the court over time under Court for a player, as for staff", () => {
    expect(layout(abilities(null, false))).toEqual({
      Troupe: ["Overview", "The setting", "Who's Who", "News", "Announcements", "Nominations", "Chronicle", "House rules"],
      Court: ["Court over time"],
    });
  });

  it("leaves a player's Court group out when the troupe doesn't share its court over time, so they see one group", () => {
    const quiet = { ...troupe, court_history_players: false };
    expect(Object.keys(layout(abilities(null, false), quiet))).toEqual(["Troupe"]);
  });

  it("names each tab's address after the tab (#1048)", () => {
    const addresses = troupeTabGroups(troupe, abilities("lead_storyteller", false)).flatMap((g) => g.tabs.map((tab) => tab.to));
    expect(addresses).toEqual([
      "/troupes/t1",
      "/troupes/t1/setting",
      "/troupes/t1/whos-who",
      "/troupes/t1/news",
      "/troupes/t1/announcements",
      "/troupes/t1/nominations",
      "/troupes/t1/chronicle",
      "/troupes/t1/staff",
      "/troupes/t1/approvals",
      "/troupes/t1/roster",
      "/troupes/t1/players",
      "/troupes/t1/lines-and-veils",
      "/troupes/t1/equipment",
      "/troupes/t1/shared-backgrounds",
      "/troupes/t1/at-game",
      "/play/troupes/t1/scenes",
      "/troupes/t1/award-xp",
      "/troupes/t1/titles",
      "/troupes/t1/court-over-time",
      "/troupes/t1/boons",
      "/troupes/t1/bonds",
      "/troupes/t1/web-of-obligation",
      "/troupes/t1/downtimes",
      "/troupes/t1/my-work",
      "/troupes/t1/fill-tables",
      "/troupes/t1/influence-log",
      "/troupes/t1/locations",
      "/troupes/t1/quests",
      "/troupes/t1/settings",
      "/troupes/t1/house-rules",
      "/troupes/t1/specialisations",
      "/troupes/t1/connectors",
      "/troupes/t1/export-and-import",
    ]);
  });

  it("keeps the Overview open on the troupe's log, which has no tab of its own, for running staff (#1048)", () => {
    const overview = (role: Parameters<typeof abilities>[0]) => troupeTabGroups(troupe, abilities(role, false))[0]!.tabs[0]!;
    expect(overview("assistant_storyteller")).toMatchObject({ label: "Overview", also: "/troupes/t1/log" });
    expect(overview("narrator").also).toBeUndefined();
  });

  it("keeps each tab in one group whoever is looking, but House rules", () => {
    const groupOf = (role: Parameters<typeof abilities>[0]) =>
      new Map(troupeTabGroups(troupe, abilities(role, false)).flatMap((g) => g.tabs.map((tab) => [tab.to, g.label] as const)));
    const lead = groupOf("lead_storyteller");
    for (const role of ["storyteller", "assistant_storyteller", "narrator", null] as const) {
      for (const [to, group] of groupOf(role)) {
        if (to === "/troupes/t1/house-rules") continue;
        expect(group, `${to} for ${role}`).toBe(lead.get(to));
      }
    }
  });

  it("puts House rules under Setting up for running staff, where they change it, and under Troupe for the rest (#782)", () => {
    const houseRulesIn = (role: Parameters<typeof abilities>[0]) =>
      troupeTabGroups(troupe, abilities(role, false)).find((g) => g.tabs.some((tab) => tab.to === "/troupes/t1/house-rules"))?.label;
    expect(houseRulesIn("lead_storyteller")).toBe("Setting up");
    expect(houseRulesIn("assistant_storyteller")).toBe("Setting up");
    expect(houseRulesIn("narrator")).toBe("Troupe");
    expect(houseRulesIn(null)).toBe("Troupe");
  });

  it("keeps a narrator's My work open inside a cycle, where their work opens (#789)", () => {
    const work = (role: Parameters<typeof abilities>[0]) =>
      troupeTabGroups(troupe, abilities(role, false))
        .find((g) => g.label === "Between games")
        ?.tabs.find((tab) => tab.label === "My work");
    expect(work("narrator")?.also).toBe("/troupes/t1/downtimes");
    expect(work("storyteller")?.also).toBeUndefined();
  });

  it("opens Characters on the roster, and Scenes on the scenes page, saying it leaves (#922)", () => {
    const groups = troupeTabGroups(troupe, abilities("storyteller", false));
    expect(groups.find((g) => g.label === "Characters")?.to).toBe("/troupes/t1/roster");
    const scenes = groups.find((g) => g.label === "Game night")?.tabs.find((tab) => tab.to === "/play/troupes/t1/scenes");
    expect(scenes).toMatchObject({ label: "Scenes ↗", ariaLabel: "Scenes (opens the scenes page)" });
  });
});
