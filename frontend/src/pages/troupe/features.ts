import type { TroupeOut } from "../../api/types";
import { BOND_SETTINGS } from "../../bonds";
import { TABS, troupeTabs } from "../play/tabs";

/** Every optional feature a troupe can have, each a row of the Features list (#783). */
export type FeatureKey =
  | "whos_who"
  | "news"
  | "play_view"
  | "boons"
  | "blood_bonds"
  | "nominations"
  | "remembrances"
  | "court_history"
  | "chronicle"
  | "quests"
  | "feeding"
  | "golconda"
  | "item_expiry";

export type Feature = {
  key: FeatureKey;
  name: string;
  /** One line on what it adds, and which tabs appear. */
  adds: string;
  on: boolean;
  /** "On", "Off", or what it is set to ("Staff manages"). */
  state: string;
  /** Its tab, under the troupe, when the troupe's staff have it. */
  tab?: { label: string; to: string };
  /**
   * Where the rest of its settings are, under the troupe: folded at the top of its own tab
   * ("boons#settings", #784), a card on Troupe settings ("#feature-feeding") or another tab
   * ("rules/quests"). None when the switch is all there is.
   */
  settings?: string;
  /** It is switched on and off from the list. Who's Who and News are always on; the Play View goes tab by tab. */
  switchable: boolean;
};

/** The id of a feature's settings card on Troupe settings, for the list to link to. */
export const settingsAnchor = (key: FeatureKey) => `feature-${key.replace(/_/g, "-")}`;

/** The id of the folded Settings at the top of a feature's own tab (#784). */
export const SETTINGS_HASH = "settings";

/** A feature's settings folded at the top of its tab: for storytellers only, as only they change them. */
const onTab = (to: string) => `${to}#${SETTINGS_HASH}`;

/** Whether a feature's settings link lands on its tab's folded Settings, which only those who may change them see. */
export const settingsOnTab = (settings: string) => settings.endsWith(`#${SETTINGS_HASH}`);

const onOff = (on: boolean) => (on ? "On" : "Off");
const requests = (n: number) => (n === 1 ? "1 request" : `${n} requests`);

/** The troupe's optional features, in the order the list shows them, each with whether it is on. */
export function features(troupe: TroupeOut): Feature[] {
  const bonds = troupe.blood_bonds ?? "off";
  const feeding = (troupe.feeding ?? "book") !== "off";
  const feedingOptions = [
    troupe.feeding_resonance && "Blood Resonance",
    troupe.feeding_territories && "feeding territories",
    troupe.feeding_rack && "the Rack",
  ].filter((o): o is string => !!o);
  const playTabs = troupeTabs(troupe);
  const everyPlayTab = TABS.filter((t) => t.key !== "boons" || troupe.boons).length;
  return [
    {
      key: "whos_who",
      name: "Who's Who",
      adds: "Every character in play, with their clan, status and titles, for the staff and the troupe's players.",
      on: true,
      state: "Always on",
      tab: { label: "Who's Who", to: "whos-who" },
      settings: onTab("whos-who"),
      switchable: false,
    },
    {
      key: "news",
      name: "News and announcements",
      adds: "Stories from the troupe's news agencies, and the staff's announcements, each with a tab of its own for the troupe's players.",
      on: !troupe.archived,
      state: troupe.archived ? "Off while archived" : "Always on",
      tab: troupe.archived ? undefined : { label: "News", to: "news" },
      settings: "news-agencies",
      switchable: false,
    },
    {
      key: "play_view",
      name: "Play View",
      adds: "The players' screen at games: their sheet, tracker, pools, throws and more, kept on the phone for games with no signal.",
      on: playTabs.length > 0,
      state: playTabs.length === 0 ? "Off for players" : playTabs.length === everyPlayTab ? "Every tab on" : `${playTabs.length} of ${everyPlayTab} tabs on`,
      tab: { label: "At game", to: "play" },
      settings: onTab("play"),
      switchable: false,
    },
    {
      key: "boons",
      name: "Boons",
      adds: "The boon ledger, registered with the Harpy: a Boons tab with its standings and statistics, and a Boons tab on the Play View.",
      on: troupe.boons,
      state: onOff(troupe.boons),
      tab: troupe.boons ? { label: "Boons", to: "boons" } : undefined,
      settings: troupe.boons ? onTab("boons") : undefined,
      switchable: true,
    },
    {
      key: "blood_bonds",
      name: "Blood bonds",
      adds: "The bonds between characters, kept by staff or by players: a Bonds tab, and a Bonds card on each sheet.",
      on: bonds !== "off",
      state: BOND_SETTINGS.find((s) => s.value === bonds)?.label ?? onOff(false),
      tab: bonds !== "off" ? { label: "Bonds", to: "bonds" } : undefined,
      settings: bonds !== "off" ? onTab("bonds") : undefined,
      switchable: true,
    },
    {
      key: "nominations",
      name: "Player Nominations",
      adds: "Players praise each other's roleplaying in their downtimes, published each month without names: a Nominations tab, and a section on the downtime form.",
      on: troupe.player_nominations,
      state: onOff(troupe.player_nominations),
      tab: troupe.player_nominations ? { label: "Nominations", to: "nominations" } : undefined,
      switchable: true,
    },
    {
      key: "remembrances",
      name: "Remembrances",
      adds: "Memories of a character who leaves play, asked of the players in the next downtime: a Remembrances tab, or a part of the Nominations tab while those are on.",
      on: troupe.remembrances,
      state: onOff(troupe.remembrances),
      // With Player Nominations on too, they share its tab, linked from its row.
      tab: troupe.remembrances && !troupe.player_nominations ? { label: "Remembrances", to: "nominations" } : undefined,
      switchable: true,
    },
    {
      key: "court_history",
      name: "The court over time, for players",
      adds: "Who held each title, and when, on a Court tab for the troupe's players: titles are public at court, but not how each one ended, nor anyone's status. Staff always have it.",
      on: troupe.court_history_players,
      state: troupe.court_history_players ? "Players see it" : "Staff only",
      tab: { label: "Court", to: "court" },
      switchable: true,
    },
    {
      key: "chronicle",
      name: "The chronicle, for players",
      adds: "The chronicle's timeline of games, downtimes and the court, on a Chronicle tab for the troupe's players: only what the troupe already shows them, not Embraces, diablerie or status. Staff always have it.",
      on: troupe.chronicle_players,
      state: troupe.chronicle_players ? "Players see it" : "Staff only",
      tab: { label: "Chronicle", to: "chronicle" },
      switchable: true,
    },
    {
      key: "quests",
      name: "Quests",
      adds: "Players ask for quests in their downtimes and staff build them: a Quests tab for staff, and one on each character.",
      on: troupe.quests_enabled,
      state: troupe.quests_enabled ? `On, ${requests(troupe.quest_requests_per_cycle)} a character each cycle` : "Off",
      tab: troupe.quests_enabled ? { label: "Quests", to: "quests" } : undefined,
      settings: "rules/quests",
      switchable: true,
    },
    {
      key: "feeding",
      name: "Feeding",
      adds: "Feeding between games: a section on the downtime form and a Feeding tab on each cycle, with Blood Resonance, feeding territories and the Rack as options.",
      on: feeding,
      state: !feeding ? "Off" : feedingOptions.length ? `On, with ${feedingOptions.join(" and ")}` : "On, as the book has it",
      settings: `#${settingsAnchor("feeding")}`,
      switchable: true,
    },
    {
      key: "golconda",
      name: "Golconda and Enlightened",
      adds: "Golconda Seekers hold the innate status Enlightened (Vol. 2, p. 267).",
      on: troupe.golconda_enlightened,
      state: onOff(troupe.golconda_enlightened),
      switchable: true,
    },
    {
      key: "item_expiry",
      name: "Items that expire",
      adds: "Staff can give an item an expiry: a day, a number of games, or the end of the cycle.",
      on: troupe.items_expire,
      state: onOff(troupe.items_expire),
      switchable: true,
    },
  ];
}
