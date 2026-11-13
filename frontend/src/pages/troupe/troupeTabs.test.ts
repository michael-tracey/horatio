import { describe, expect, it } from "vitest";
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

/** Each shown group with its tabs' labels. */
function layout(can: ReturnType<typeof abilities>, t: TroupeTabsTroupe = troupe) {
  return Object.fromEntries(
    troupeTabGroups(t, can)
      .filter((g) => g.tabs.length > 0)
      .map((g) => [g.label, g.tabs.map((tab) => tab.label)]),
  );
}

const storytellerLayout = {
  Troupe: ["About", "Profile", "Who's Who", "News", "Announcements", "Nominations", "House rules", "Status", "Staff", "Log"],
  Characters: ["Approvals", "Being built", "Characters", "Players", "Lines and veils"],
  Games: ["At game", "Scenes", "Award XP"],
  Court: ["Titles", "Court", "Chronicle", "Boons", "Bonds", "Web of obligation"],
  Downtimes: ["Cycles", "My work", "Fill tables", "Influence log", "Quests"],
  World: ["Locations", "Equipment", "Shared backgrounds"],
  Customise: ["Overview", "Troupe settings", "Rules", "Specialisations", "News", "Connectors", "Share settings"],
};

describe("troupeTabGroups (#779)", () => {
  it("groups a lead storyteller's tabs by job", () => {
    expect(layout(abilities("lead_storyteller", false))).toEqual(storytellerLayout);
  });

  it("gives a storyteller and an assistant storyteller the same groups as the lead", () => {
    expect(layout(abilities("storyteller", false))).toEqual(storytellerLayout);
    expect(layout(abilities("assistant_storyteller", false))).toEqual(storytellerLayout);
  });

  it("gives a narrator the troupe, lines and veils, and their downtime work", () => {
    expect(layout(abilities("narrator", false))).toEqual({
      Troupe: ["About", "Profile", "Who's Who", "News", "Announcements", "Nominations", "House rules", "Status", "Staff"],
      Characters: ["Lines and veils"],
      Court: ["Court", "Chronicle"],
      Downtimes: ["My work", "Fill tables", "Quests"],
    });
  });

  it("puts Court and Chronicle under Court for a player, as for staff", () => {
    expect(layout(abilities(null, false))).toEqual({
      Troupe: ["About", "Profile", "Who's Who", "News", "Announcements", "Nominations", "House rules", "Status"],
      Court: ["Court", "Chronicle"],
    });
  });

  it("leaves a player's Court group out when the troupe shares neither", () => {
    const quiet = { ...troupe, court_history_players: false, chronicle_players: false };
    expect(Object.keys(layout(abilities(null, false), quiet))).toEqual(["Troupe"]);
  });

  it("keeps each tab in one group whoever is looking", () => {
    const groupOf = (role: Parameters<typeof abilities>[0]) =>
      new Map(troupeTabGroups(troupe, abilities(role, false)).flatMap((g) => g.tabs.map((tab) => [tab.to, g.label] as const)));
    const lead = groupOf("lead_storyteller");
    for (const role of ["storyteller", "assistant_storyteller", "narrator", null] as const) {
      for (const [to, group] of groupOf(role)) expect(group, `${to} for ${role}`).toBe(lead.get(to));
    }
  });

  it("keeps a narrator's My work open inside a cycle, where their work opens (#789)", () => {
    const work = (role: Parameters<typeof abilities>[0]) =>
      troupeTabGroups(troupe, abilities(role, false))
        .find((g) => g.label === "Downtimes")
        ?.tabs.find((tab) => tab.label === "My work");
    expect(work("narrator")?.also).toBe("/troupes/t1/downtimes");
    expect(work("storyteller")?.also).toBeUndefined();
  });

  it("opens Characters on the roster, and Scenes on the scenes page", () => {
    const groups = troupeTabGroups(troupe, abilities("storyteller", false));
    expect(groups.find((g) => g.label === "Characters")?.to).toBe("/troupes/t1/characters");
    expect(groups.find((g) => g.label === "Games")?.tabs.find((tab) => tab.label === "Scenes")?.to).toBe("/play/troupes/t1/scenes");
  });
});
