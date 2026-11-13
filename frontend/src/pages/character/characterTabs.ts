import type { GroupedTabs } from "../../components/ui";

export type TabGroup = Parameters<typeof GroupedTabs>[0]["groups"][number];

/** What decides which of a player character's tabs show. */
export type TabsFor = {
  base: string;
  /** Its player is looking. */
  mine: boolean;
  /** Its player is still creating it. */
  creating: boolean;
  /** Its home troupe's storytellers and assistants are looking, and it runs quests. */
  staffQuests: boolean;
  /** A troupe it is in runs quests. */
  questsOn: boolean;
  influence: boolean;
  keepsProjects: boolean;
  shared: boolean;
  backstory: boolean;
  /** The counts on Downtime and Results. */
  due: number;
  newResults: number;
};

/**
 * Who sees the Quests tab, and as whom (#788): its player sees their own quests, its
 * home troupe's running staff see them read-only with links to manage them. Its player
 * wins when both are true, so there is never a second tab named Quests.
 */
export function questsView({ mine, creating, staffQuests, questsOn }: Pick<TabsFor, "mine" | "creating" | "staffQuests" | "questsOn">): "player" | "staff" | null {
  if (!questsOn) return null;
  if (mine) return creating ? null : "player";
  return staffQuests ? "staff" : null;
}

/** A player character's tabs, in groups. */
export function characterTabGroups(t: TabsFor): TabGroup[] {
  const { base, mine, creating } = t;
  const quests = questsView(t);
  const questsTab = { to: `${base}/quests`, label: "Quests" };
  return [
    { label: "Create", tabs: creating ? [{ to: `${base}/create`, label: "Create" }] : [] },
    {
      label: "Sheet",
      tabs: [
        { to: base, label: "Sheet", end: true },
        { to: `${base}/status`, label: "Status & Titles" },
        { to: `${base}/equipment`, label: "Equipment" },
        ...(creating ? [] : [{ to: `${base}/xp`, label: "Experience" }]),
        ...(t.shared ? [{ to: `${base}/shared`, label: "Shared backgrounds" }] : []),
      ],
    },
    {
      label: "Between games",
      tabs: [
        ...(mine && !creating
          ? [
              { to: `${base}/downtime`, label: "Downtime", count: t.due, countLabel: "due" },
              { to: `${base}/results`, label: "Results", count: t.newResults, countLabel: "new" },
            ]
          : []),
        ...(quests === "player" ? [questsTab] : []),
        ...(t.influence && !creating ? [{ to: `${base}/influence`, label: "Influence" }] : []),
        ...(t.keepsProjects && !creating ? [{ to: `${base}/projects`, label: "Projects" }] : []),
        ...(quests === "staff" ? [questsTab] : []),
      ],
    },
    {
      label: "About",
      tabs: [
        ...(mine ? [{ to: `${base}/troupes`, label: "Troupes" }] : []),
        ...(t.backstory ? [{ to: `${base}/backstory`, label: "Backstory" }] : []),
        { to: `${base}/log`, label: "Log" },
      ],
    },
  ];
}

/** Labels that more than one tab carries, across all the groups: none, ever. */
export function repeatedLabels(groups: TabGroup[]): string[] {
  const labels = groups.flatMap((g) => g.tabs.map((tab) => tab.label));
  return [...new Set(labels.filter((l, i) => labels.indexOf(l) !== i))];
}
