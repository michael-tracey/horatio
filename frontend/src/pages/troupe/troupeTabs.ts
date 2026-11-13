import type { GroupedTabs } from "../../components/ui";
import type { TroupeOut } from "../../api/types";
import type { abilities } from "./roles";

export type TabGroup = Parameters<typeof GroupedTabs>[0]["groups"][number];

/** What of the troupe decides which tabs show. */
export type TroupeTabsTroupe = Pick<
  TroupeOut,
  "id" | "archived" | "whos_who" | "nominations" | "player_nominations" | "court_history_players" | "chronicle_players" | "blood_bonds" | "boons" | "quests_enabled"
>;

/** The counts on the tabs: what waits on the staff member, and what's unread. */
export type TroupeTabCounts = {
  approvals?: number;
  characters?: number;
  downtimes?: number;
  work?: number;
  influence?: number;
  quests?: number;
  building?: number;
  newsUnread?: number;
  announcementsUnread?: number;
};

/**
 * A troupe's tabs, grouped by job (#779). A tab sits in the same group whoever is
 * looking, but for House rules (#782); each sees only the tabs they may open, and a
 * group with none is left out.
 */
export function troupeTabGroups(t: TroupeTabsTroupe, can: ReturnType<typeof abilities>, counts: TroupeTabCounts = {}): TabGroup[] {
  const base = `/troupes/${t.id}`;
  const live = !t.archived;
  const bonds = (t.blood_bonds ?? "off") !== "off";
  const houseRules = { to: `${base}/house-rules`, label: "House rules" };
  return [
    {
      // The troupe itself: who's in it, what it says, and how it plays.
      label: "Troupe",
      tabs: [
        // About and Profile in one (#781): the old profile address comes here.
        { to: base, label: "Overview", end: true },
        // The Setting Style Document, for everyone to read before they build (#771).
        { to: `${base}/setting`, label: "Setting" },
        ...(t.whos_who ? [{ to: `${base}/whos-who`, label: "Who's Who" }] : []),
        ...(t.whos_who && live ? [{ to: `${base}/news`, label: "News", count: counts.newsUnread ?? 0, countLabel: "unread" }] : []),
        ...(t.whos_who && live ? [{ to: `${base}/announcements`, label: "Announcements", count: counts.announcementsUnread ?? 0, countLabel: "unread" }] : []),
        ...(t.nominations ? [{ to: `${base}/nominations`, label: t.player_nominations ? "Nominations" : "Remembrances" }] : []),
        // The one tab read and edited in the same place (#782): players and narrators read it here,
        // running staff find it under Customise, where they change it.
        ...(!can.running ? [houseRules] : []),
        ...(can.staff ? [{ to: `${base}/staff`, label: "Staff" }] : []),
        ...(can.running ? [{ to: `${base}/log`, label: "Log" }] : []),
      ],
    },
    {
      // Approvals first, as what most often waits; the group still opens on the roster.
      label: "Characters",
      to: `${base}/characters`,
      tabs: [
        ...(can.running ? [{ to: `${base}/approvals`, label: "Approvals", count: counts.approvals }] : []),
        ...(can.running && live ? [{ to: `${base}/being-built`, label: "Being built", count: counts.building ?? 0, countLabel: "being built", countInGroup: false }] : []),
        ...(can.running ? [{ to: `${base}/characters`, label: "Characters", count: counts.characters }] : []),
        ...(can.running ? [{ to: `${base}/players`, label: "Players" }] : []),
        ...(can.staff ? [{ to: `${base}/lines-veils`, label: "Lines and veils" }] : []),
      ],
    },
    {
      // Running a game night: Scenes opens the scenes page, outside the troupe's tabs.
      label: "Games",
      tabs: [
        ...(can.running ? [{ to: `${base}/play`, label: "At game" }] : []),
        ...(can.running ? [{ to: `/play/troupes/${t.id}/scenes`, label: "Scenes" }] : []),
        ...(can.running ? [{ to: `${base}/xp`, label: "Award XP" }] : []),
      ],
    },
    {
      // The court and the debts and bonds between its members.
      label: "Court",
      tabs: [
        ...(can.running ? [{ to: `${base}/titles`, label: "Titles" }] : []),
        ...(can.running || (t.whos_who && t.court_history_players) ? [{ to: `${base}/court`, label: "Court" }] : []),
        ...(can.running || (t.whos_who && t.chronicle_players) ? [{ to: `${base}/chronicle`, label: "Chronicle" }] : []),
        ...(can.running && t.boons ? [{ to: `${base}/boons`, label: "Boons" }] : []),
        ...(can.running && bonds ? [{ to: `${base}/bonds`, label: "Bonds" }] : []),
        ...(can.running ? [{ to: `${base}/obligations`, label: "Web of obligation" }] : []),
      ],
    },
    {
      label: "Downtimes",
      tabs: [
        ...(can.running ? [{ to: `${base}/downtimes`, label: "Cycles", count: counts.downtimes }] : []),
        // A narrator's cycle opens on their own work in it, so My work stays open there (#789).
        ...(can.staff ? [{ to: `${base}/work`, label: "My work", count: counts.work, ...(can.running ? {} : { also: `${base}/downtimes` }) }] : []),
        ...(can.staff ? [{ to: `${base}/tables`, label: "Fill tables" }] : []),
        ...(can.running ? [{ to: `${base}/influence`, label: "Influence log", count: counts.influence }] : []),
        ...(can.staff && t.quests_enabled ? [{ to: `${base}/quests`, label: "Quests", count: counts.quests }] : []),
      ],
    },
    {
      // The troupe's own catalogues: places, things and backgrounds characters share.
      label: "World",
      tabs: [
        ...(can.running ? [{ to: `${base}/locations`, label: "Locations" }] : []),
        ...(can.running ? [{ to: `${base}/equipment`, label: "Equipment" }] : []),
        ...(can.running ? [{ to: `${base}/shared`, label: "Shared backgrounds" }] : []),
      ],
    },
    {
      label: "Customise",
      tabs: [
        ...(can.running ? [{ to: `${base}/customise`, label: "Overview" }] : []),
        ...(can.running ? [{ to: `${base}/settings`, label: "Troupe settings" }] : []),
        ...(can.running ? [houseRules] : []),
        ...(can.running ? [{ to: `${base}/specializations`, label: "Specialisations" }] : []),
        ...(can.running ? [{ to: `${base}/news-agencies`, label: "News agencies" }] : []),
        ...(can.running ? [{ to: `${base}/connectors`, label: "Connectors" }] : []),
        ...(can.running ? [{ to: `${base}/share`, label: "Share settings" }] : []),
      ],
    },
  ];
}
