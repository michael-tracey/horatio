// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { TroupeOut } from "../../api/types";
import { settingsSource } from "../../search/search";
import { features, PART_HOMES, settingsPart, SETTINGS_HASH, type SettingsPart } from "./features";
import { abilities } from "./roles";
import { findSettings, RULE_SECTIONS, SETTINGS, SETTINGS_DIALOGS, settingsIndex, TROUPE_SETTINGS_PARTS, type CardSetting } from "./settingsIndex";
import { troupeTabGroups } from "./troupeTabs";

// Every feature on, so every tab, dialog and card is there to be found.
const TROUPE = {
  id: "t1",
  name: "Court of Ash",
  archived: false,
  my_role: "storyteller",
  whos_who: true,
  boons: true,
  blood_bonds: "staff",
  player_nominations: true,
  remembrances: true,
  nominations: true,
  court_history_players: true,
  chronicle_players: true,
  quests_enabled: true,
  quest_requests_per_cycle: 1,
  feeding: "book",
  feeding_resonance: false,
  feeding_territories: true,
  feeding_rack: false,
  golconda_enlightened: false,
  items_expire: false,
  play_tabs_off: [],
} as unknown as TroupeOut;

const storyteller = abilities("storyteller", false);
const titles = (t: TroupeOut = TROUPE, can = storyteller) => settingsIndex(t, can).map((e) => e.title);

/** The source of the troupe's screens and the news screens, News › Agencies among them. */
function sources(dir: URL): { file: string; text: string }[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((f) =>
    f.isDirectory() ? sources(new URL(`${f.name}/`, dir)) : /\.tsx?$/.test(f.name) && !/\.test\./.test(f.name) ? [{ file: f.name, text: readFileSync(new URL(f.name, dir), "utf8") }] : [],
  );
}
const screens = [...sources(new URL("./", import.meta.url)), ...sources(new URL("../news/", import.meta.url))];

describe("the settings index", () => {
  it("has every settings card of a troupe's screens: each card is drawn from its entry", () => {
    // A troupe's card names its entry first, `<SettingCard setting={SETTINGS.…}`, so a new card
    // without one fails here. A person's own settings (pages/settings) are not a troupe's.
    const without = screens.flatMap(({ file, text }) => [...text.matchAll(/<SettingCard\b(?!\s+setting=\{)/g)].map(() => file));
    expect(without).toEqual([]);
    const cards = screens.reduce((n, { text }) => n + (text.match(/<SettingCard\b/g)?.length ?? 0), 0);
    expect(cards).toBeGreaterThanOrEqual(Object.keys(SETTINGS).length);
  });

  it("has no entry that no card is drawn from", () => {
    const all = screens.filter((s) => s.file !== "settingsIndex.ts").map((s) => s.text).join("\n");
    const unused = Object.keys(SETTINGS).filter((key) => !new RegExp(`SETTINGS\\.${key}\\b`).test(all));
    expect(unused).toEqual([]);
  });

  it("has every tab's Settings dialog, each drawn with its entry's name, at a tab of the troupe", () => {
    const featureSettings = screens.find((s) => s.file === "FeatureSettings.tsx")!.text;
    expect([...featureSettings.matchAll(/<FeatureSettings\b(?!\s+tab=\{SETTINGS_DIALOGS\[)/g)]).toEqual([]);
    const page = screens.find((s) => s.file === "TroupePage.tsx")!.text;
    for (const d of Object.values(SETTINGS_DIALOGS)) expect(page).toMatch(new RegExp(`path="${d.to}(/\\*)?"`));
    for (const d of Object.values(SETTINGS_DIALOGS)) expect(titles()).toContain(`${d.tab} settings`);
  });

  it("gives each card an id of its own, apart from the dialogs' parts", () => {
    const anchors = Object.values(SETTINGS as Record<string, CardSetting>).map((s) => s.anchor);
    expect(new Set(anchors).size).toBe(anchors.length);
    const parts = (Object.keys(PART_HOMES) as SettingsPart[]).map(settingsPart);
    expect(anchors.filter((a) => parts.includes(a) || a === SETTINGS_HASH)).toEqual([]);
  });

  it("finds every Setting up tab, part, feature, dialog and card of a troupe with every feature on", () => {
    const found = titles();
    const can = storyteller;
    const settingUp = troupeTabGroups(TROUPE, can).find((g) => g.label === "Setting up")!.tabs.map((t) => t.label);
    expect(settingUp.length).toBeGreaterThan(0);
    for (const label of settingUp) expect(found).toContain(label);
    expect(found).toContain("Getting ready");
    expect(found).toContain("News agencies");
    for (const p of TROUPE_SETTINGS_PARTS) expect(found).toContain(p.label);
    for (const s of RULE_SECTIONS) expect(found).toContain(s.label);
    for (const f of features(TROUPE)) expect(found).toContain(f.name);
    for (const s of Object.values(SETTINGS)) expect(found).toContain(s.title);
    const addresses = settingsIndex(TROUPE, can).map((e) => e.to);
    expect(new Set(addresses).size).toBe(addresses.length);
  });

  it("opens each card where it is: its part of Settings, or its tab's Settings, at its card", () => {
    const at = (title: string, where: string) => settingsIndex(TROUPE, storyteller).find((e) => e.title === title && e.where === where)?.to;
    expect(at("XP floor and ceiling", "Settings › XP")).toBe("/troupes/t1/settings/xp#settings-xp-range");
    expect(at("Boons", "Boons settings")).toBe("/troupes/t1/boons#settings-boon-ledger");
    expect(at("Teachers", "Approvals settings")).toBe("/troupes/t1/approvals#settings-teacher-rules");
    expect(at("Boons settings", "Boons tab")).toBe("/troupes/t1/boons#settings");
    expect(at("Golconda and Enlightened", "Settings › Features")).toBe("/troupes/t1/settings#switch-golconda");
    expect(at("Getting ready", "Settings")).toBe("/troupes/t1/settings/getting-ready");
    expect(at("News agencies", "News")).toBe("/troupes/t1/news/agencies");
    expect(at("Costs", "House rules")).toBe("/troupes/t1/house-rules/costs");
  });

  it("leaves out what the troupe doesn't have: a feature's tab and dialog while it's off", () => {
    const off = { ...TROUPE, boons: false, blood_bonds: "off", quests_enabled: false, feeding_territories: false } as TroupeOut;
    const found = settingsIndex(off, storyteller);
    expect(found.filter((e) => e.where === "Boons settings" || e.title === "Boons settings")).toEqual([]);
    expect(found.map((e) => e.title)).not.toContain("Bonds settings");
    expect(found.map((e) => e.title)).not.toContain("Quest requests");
    expect(found.map((e) => e.title)).not.toContain("Feeding territories");
    // Still switched on and off in the Features list.
    expect(found.find((e) => e.title === "Boons")?.where).toBe("Settings › Features");
  });

  it("is for those who may open the settings: running staff and the custodian, nobody else", () => {
    expect(titles(TROUPE, abilities("lead_storyteller", false))).toContain("Sects");
    expect(titles(TROUPE, abilities("assistant_storyteller", false))).toContain("Sects");
    expect(titles(TROUPE, abilities(null, true))).toContain("Sects");
    expect(titles(TROUPE, abilities("narrator", false))).toEqual([]);
    expect(titles(TROUPE, abilities(null, false))).toEqual([]);
  });
});

describe("finding a setting", () => {
  const index = settingsIndex(TROUPE, storyteller);
  const find = (q: string) => findSettings(index, q).map((e) => e.title);

  it("finds part of a name in any case, those it starts first", () => {
    expect(find("xp")[0]).toBe("XP");
    expect(find("xp")).toContain("XP floor and ceiling");
    expect(find("FLOOR")[0]).toBe("XP floor and ceiling");
    expect(find("ceil")).toContain("XP floor and ceiling");
  });

  it("finds every word, in any order, in the name, the place or the line", () => {
    expect(find("status night")).toContain("The night's status");
    expect(find("night’s status")).toContain("The night's status");
    expect(find("discord")).toContain("Connectors");
    expect(find("assamite")).toEqual(["Banu Haqim or Assamite"]);
    expect(find("zzzz")).toEqual([]);
    expect(find("   ")).toEqual([]);
  });
});

describe("the top bar's settings", () => {
  it("are the troupe's the person is on, for its storytellers alone", async () => {
    const hits = await settingsSource.find("sects", { troupeId: "t1", troupe: TROUPE, custodian: false });
    expect(hits[0]).toMatchObject({ title: "Sects", to: "/troupes/t1/settings/joining#settings-sects", troupe_id: "t1" });
    expect(hits[0]?.detail).toMatch(/^Settings › Who may join · Which sects/);
    expect(await settingsSource.find("sects", { troupeId: null })).toEqual([]);
    expect(await settingsSource.find("sects", { troupeId: "t1", troupe: { ...TROUPE, my_role: "lead_storyteller" } })).not.toEqual([]);
    // An assistant storyteller finds them on Setting up, but not from the top bar (#1133).
    expect(await settingsSource.find("sects", { troupeId: "t1", troupe: { ...TROUPE, my_role: "assistant_storyteller" } })).toEqual([]);
    expect(findSettings(settingsIndex(TROUPE, abilities("assistant_storyteller", false)), "sects")).not.toEqual([]);
    expect(await settingsSource.find("sects", { troupeId: "t1", troupe: { ...TROUPE, my_role: "narrator" } })).toEqual([]);
    expect(await settingsSource.find("sects", { troupeId: "t1", troupe: { ...TROUPE, my_role: null } })).toEqual([]);
    expect(await settingsSource.find("sects", { troupeId: "t1", troupe: { ...TROUPE, my_role: null }, custodian: true })).not.toEqual([]);
  });
});
