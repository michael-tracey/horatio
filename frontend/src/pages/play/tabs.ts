import type { PlayView, TroupeOut } from "../../api/types";

/** A tab of the Play View, as the server names it (horatio.play_tabs). */
export type Tab = PlayView["tabs"][number];

/**
 * The Play View's tabs, in order. A troupe switches each one on or off for its
 * players (#673): its settings make a switch for each tab here, so a tab added here
 * gets one. The server's list (horatio.play_tabs.PlayTab) gains it too.
 */
export const TABS = [
  { key: "sheet", label: "Sheet" },
  { key: "tracker", label: "Tracker" },
  { key: "pools", label: "Pools" },
  // Only for a character with sect status.
  { key: "status", label: "Status" },
  { key: "equipment", label: "Equipment" },
] as const satisfies readonly { key: Tab; label: string }[];

// Every tab the server knows is in TABS: one missing here fails the typecheck.
type Missing = Exclude<Tab, (typeof TABS)[number]["key"]>;
export const EVERY_TAB_LISTED: [Missing] extends [never] ? true : Missing = true;

/** The tabs a troupe has on, with `off` switched off. */
export function tabsOn(off: readonly string[]): Tab[] {
  return TABS.map((t) => t.key).filter((key) => !off.includes(key));
}

/** Whether a troupe uses the Play View: any of its tabs is on. */
export function usesPlayView(troupe: Pick<TroupeOut, "play_tabs_off">): boolean {
  return tabsOn(troupe.play_tabs_off).length > 0;
}

/** The tabs a character's Play View shows: those it has, and Status only with sect status. */
export function shownTabs(tabs: readonly Tab[], status: boolean): Tab[] {
  return TABS.map((t) => t.key).filter((key) => tabs.includes(key) && (key !== "status" || status));
}

/** The tab the Play View opens on: the one a link asks for, else the person's choice in
 * Settings, else the first one shown, when its troupe has switched those off. */
export function openingTab(asked: string | null, preferred: Tab, shown: readonly Tab[]): Tab | undefined {
  return shown.find((t) => t === asked) ?? (shown.includes(preferred) ? preferred : shown[0]);
}

/** "Sheet, Tracker and Pools". */
export function tabNames(keys: readonly Tab[]): string {
  const named = TABS.filter((t) => keys.includes(t.key)).map((t) => t.label);
  return named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}` : (named[0] ?? "");
}

/**
 * Settings › the Play View opens on: the tabs offered are those at least one of the
 * person's troupes has on (all of them with no troupe), and for each choice a troupe
 * has switched off, which troupes did.
 */
export function openingChoices<T extends Tab>(choices: readonly T[], troupes: readonly Pick<TroupeOut, "name" | "play_tabs_off">[]): { offered: T[]; off: { tab: T; troupes: string[] }[] } {
  const using = troupes.filter((t) => usesPlayView(t));
  const offered = choices.filter((c) => using.length === 0 || using.some((t) => !t.play_tabs_off.includes(c)));
  const off = choices.map((tab) => ({ tab, troupes: using.filter((t) => t.play_tabs_off.includes(tab)).map((t) => t.name) })).filter((o) => o.troupes.length > 0);
  return { offered, off };
}
