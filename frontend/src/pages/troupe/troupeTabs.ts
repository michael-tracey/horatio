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
  newsUnread?: number;
  announcementsUnread?: number;
};

/**
 * A troupe's tabs, grouped by what staff are doing (#779, #1048): what everyone reads,
 * the characters, a game night, the court, between games, and setting up. A tab sits
 * in the same group whoever is looking, but for House rules (#782); each sees only
 * the tabs they may open, and a group with none is left out. Each tab's address is
 * its name (#1048); the old ones go to the new (`TroupePage`).
 */
export function troupeTabGroups(t: TroupeTabsTroupe, can: ReturnType<typeof abilities>, counts: TroupeTabCounts = {}): TabGroup[] {
  const base = `/troupes/${t.id}`;
  const live = !t.archived;
  const bonds = (t.blood_bonds ?? "off") !== "off";
  const houseRules = { to: `${base}/house-rules`, label: "House rules" };
  return [
    {
      // What everyone in the troupe reads.
      label: "Troupe",
      tabs: [
        // About and Profile in one (#781), with the latest of the log for running staff,
        // whose page opens from there (#1048).
        { to: base, label: "Overview", end: true, ...(can.running ? { also: `${base}/log` } : {}) },
        // The Setting Style Document, for everyone to read before they build (#771), and
        // for running staff its staff-only companion, the story bible, as a part (#879).
        { to: `${base}/setting`, label: "The setting" },
        ...(t.whos_who ? [{ to: `${base}/whos-who`, label: "Who's Who" }] : []),
        ...(t.whos_who && live ? [{ to: `${base}/news`, label: "News", count: counts.newsUnread ?? 0, countLabel: "unread" }] : []),
        ...(t.whos_who && live ? [{ to: `${base}/announcements`, label: "Announcements", count: counts.announcementsUnread ?? 0, countLabel: "unread" }] : []),
        ...(t.nominations ? [{ to: `${base}/nominations`, label: t.player_nominations ? "Nominations" : "Remembrances" }] : []),
        // The story so far, beside the setting and the news it grew from.
        ...(can.running || (t.whos_who && t.chronicle_players) ? [{ to: `${base}/chronicle`, label: "Chronicle" }] : []),
        // The one tab read and edited in the same place (#782): players and narrators read it here,
        // running staff find it under Setting up, where they change it.
        ...(!can.running ? [houseRules] : []),
        ...(can.staff ? [{ to: `${base}/staff`, label: "Staff" }] : []),
      ],
    },
    {
      // The people and their records, any time. Approvals first, as what most often waits,
      // with what is being built as a part of it (#774); the group still opens on the roster.
      label: "Characters",
      to: `${base}/roster`,
      tabs: [
        ...(can.running ? [{ to: `${base}/approvals`, label: "Approvals", count: counts.approvals }] : []),
        ...(can.running ? [{ to: `${base}/roster`, label: "Roster", count: counts.characters }] : []),
        ...(can.running ? [{ to: `${base}/players`, label: "Players" }] : []),
        ...(can.staff ? [{ to: `${base}/lines-and-veils`, label: "Lines and veils" }] : []),
        ...(can.running ? [{ to: `${base}/equipment`, label: "Equipment" }] : []),
        ...(can.running ? [{ to: `${base}/shared-backgrounds`, label: "Shared backgrounds" }] : []),
      ],
    },
    {
      // Running a game night: Scenes opens the scenes page, outside the troupe's tabs,
      // and says so (#922).
      label: "Game night",
      tabs: [
        // Open on a game's own page too, which its breadcrumb puts under At game.
        ...(can.running ? [{ to: `${base}/at-game`, label: "At game", also: `${base}/games` }] : []),
        ...(can.running ? [{ to: `/play/troupes/${t.id}/scenes`, label: "Scenes ↗", ariaLabel: "Scenes (opens the scenes page)" }] : []),
        ...(can.running ? [{ to: `${base}/award-xp`, label: "Award XP" }] : []),
      ],
    },
    {
      // The court, its titles over time, and the debts and bonds between its members.
      label: "Court",
      tabs: [
        ...(can.running ? [{ to: `${base}/titles`, label: "Titles" }] : []),
        ...(can.running || (t.whos_who && t.court_history_players) ? [{ to: `${base}/court-over-time`, label: "Court over time" }] : []),
        ...(can.running && t.boons ? [{ to: `${base}/boons`, label: "Boons" }] : []),
        ...(can.running && bonds ? [{ to: `${base}/bonds`, label: "Bonds" }] : []),
        ...(can.running ? [{ to: `${base}/web-of-obligation`, label: "Web of obligation" }] : []),
      ],
    },
    {
      // Downtimes and what feeds them.
      label: "Between games",
      tabs: [
        ...(can.running ? [{ to: `${base}/downtimes`, label: "Downtimes", count: counts.downtimes }] : []),
        // A narrator's cycle opens on their own work in it, so My work stays open there (#789).
        ...(can.staff ? [{ to: `${base}/my-work`, label: "My work", count: counts.work, ...(can.running ? {} : { also: `${base}/downtimes` }) }] : []),
        ...(can.staff ? [{ to: `${base}/fill-tables`, label: "Fill tables" }] : []),
        ...(can.running ? [{ to: `${base}/influence-log`, label: "Influence log", count: counts.influence }] : []),
        ...(can.running ? [{ to: `${base}/locations`, label: "Locations" }] : []),
        ...(can.staff && t.quests_enabled ? [{ to: `${base}/quests`, label: "Quests", count: counts.quests }] : []),
      ],
    },
    {
      // Set once a season or so.
      label: "Setting up",
      tabs: [
        ...(can.running ? [{ to: `${base}/settings`, label: "Settings" }] : []),
        ...(can.running ? [houseRules] : []),
        ...(can.running ? [{ to: `${base}/specialisations`, label: "Specialisations" }] : []),
        ...(can.running ? [{ to: `${base}/connectors`, label: "Connectors" }] : []),
        ...(can.running ? [{ to: `${base}/export-and-import`, label: "Export and import" }] : []),
      ],
    },
  ];
}
