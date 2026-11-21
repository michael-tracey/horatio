import type { TroupeOut } from "../../api/types";
import { BOND_PAGE } from "../../bonds";
import { BOON_PAGE } from "../../boons";
import { features, SETTINGS_HASH, type FeatureKey, type TroupeSettingsPart } from "./features";
import type { abilities } from "./roles";
import { troupeTabGroups } from "./troupeTabs";

/**
 * Every setting of a troupe by name (#1047), for the Find a setting box on Customise and the
 * top bar's search: the Customise tabs, the parts of Troupe settings and House rules, each
 * feature's switch, each tab's Settings dialog and every settings card. The cards take their
 * titles and lines from `SETTINGS` here, and the tabs, parts and features are read from the
 * lists their screens are drawn from, so what is found is what the screen says.
 */

/** The parts of Troupe settings after the Features list, in order (#908). */
export const TROUPE_SETTINGS_PARTS: { part: TroupeSettingsPart; label: string }[] = [
  { part: "setting", label: "The setting" },
  { part: "joining", label: "Who may join" },
  { part: "xp", label: "XP" },
  { part: "status", label: "Status and titles" },
  { part: "blood", label: "Blood, diablerie and feeding" },
  { part: "names", label: "Names" },
];

/** The parts of the house rules staff change, each a part of the House rules tab (#782). */
export const RULE_SECTIONS = [
  { path: "checks", label: "Checks" },
  { path: "costs", label: "Costs" },
  { path: "starting", label: "Starting points" },
  { path: "actions", label: "Downtime actions" },
  { path: "keywords", label: "Downtime keywords" },
  { path: "languages", label: "Languages" },
  { path: "house-traits", label: "House merits and flaws" },
  { path: "written", label: "Written rules" },
  { path: "book-traits", label: "Book traits" },
] as const;

/**
 * The tabs with a Settings button of their own (#784, #785, #909): each tab's name, for its
 * dialog's title, and its address under the troupe. A dialog is found only where its tab is.
 */
export const SETTINGS_DIALOGS = {
  whos_who: { tab: "Who's Who", to: "whos-who" },
  play_view: { tab: "At game", to: "play" },
  boons: { tab: "Boons", to: "boons" },
  blood_bonds: { tab: "Bonds", to: "bonds" },
  locations: { tab: "Locations", to: "locations" },
  quests: { tab: "Quests", to: "quests" },
  characters: { tab: "Roster", to: "characters" },
  approvals: { tab: "Approvals", to: "approvals" },
} as const;

export type SettingsDialog = keyof typeof SETTINGS_DIALOGS;

/** Where a card is: the Features list, a part of Troupe settings, or a tab's Settings dialog. */
type CardPlace = "features" | TroupeSettingsPart | SettingsDialog;

/** A settings card: its title and the line under it, where it is, and the id it lands on. */
export type CardSetting = {
  title: string;
  about: string;
  in: CardPlace;
  /** Its card's id: an address ending `#<anchor>` scrolls to it, and in a dialog opens the dialog too. */
  anchor: string;
  /** Only while the troupe shows it, beyond its place being there. */
  shown?: (t: TroupeOut) => boolean;
};

const card = (key: string, title: string, about: string, place: CardPlace, shown?: (t: TroupeOut) => boolean): CardSetting => ({
  title,
  about,
  in: place,
  anchor: `${SETTINGS_HASH}-${key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`,
  shown,
});

/**
 * Every settings card of a troupe, each card drawn with its own (`<SettingCard setting={…}>`).
 * A line a card writes out itself, with a link or a number in it, is here in plain words.
 */
export const SETTINGS = {
  features: card(
    "features",
    "Features",
    "What the troupe uses beyond the sheets and downtimes. Switched off, a feature's tabs are hidden, and what was recorded is kept for when it's on again.",
    "features",
  ),

  whereRead: card(
    "whereRead",
    "Where players read it",
    "Every member reads the whole document on the Setting tab, with the parts built from the troupe's settings: its sects, clan rarities, costs and mechanics. A character built to the troupe's rules shows its themes, moods and teaser as it is made.",
    "setting",
  ),
  titleTeaser: card("titleTeaser", "Title and teaser", "The chronicle's name, and the chronicle as its characters know it.", "setting"),
  scope: card("scope", "Scope", "Where the chronicle is, and how far its characters reach (MET: VTM pp. 329–330).", "setting"),
  themes: card("themes", "Themes", "", "setting"),
  moods: card("moods", "Moods", "", "setting"),
  storytellerNotes: card("storytellerNotes", "Storyteller notes", "", "setting"),

  splats: card(
    "splats",
    "Splats",
    "Which splats player characters may be. Tick at least one: new characters built for the troupe, and those joining it, must be one of these. NPCs are not limited.",
    "joining",
  ),
  sects: card("sects", "Sects", "Which sects player characters may join from. Leave all unticked to take any sect. NPCs are not limited.", "joining"),

  experience: card(
    "experience",
    "Experience",
    "What this troupe usually gives. Awarding XP starts at the session amount, and each new downtime cycle at the completion amount; either can be changed there. The XP floor and ceiling start from the starting XP.",
    "xp",
  ),
  xpRange: card(
    "xpRange",
    "XP floor and ceiling",
    "The ceiling is the most XP a character here could have by now: the starting XP, every game's XP and every downtime's XP. The floor leaves out the downtimes. New characters built for this troupe start at the floor.",
    "xp",
  ),
  gameXp: card(
    "gameXp",
    "Game XP chart",
    "How much XP a game gives each character. The book suggests 3 to 5 a game and no more than 8 to 10 a month (MET: VtM core, p. 108). A chart tapers it by how much XP a character has earned in all, not counting starting XP or what joining gave.",
    "xp",
  ),
  newCharacterIncentive: card(
    "newCharacterIncentive",
    "New Character Incentive",
    "Without it, a new character built here starts at the XP floor. With it, as the book's optional rule has it (p. 349), a new character starts with the starting XP and a quarter of the XP a character could have earned here. Characters already made keep their XP.",
    "xp",
  ),

  statusOnSheets: card(
    "statusOnSheets",
    "Status on sheets",
    "Who adds and removes sect status on the sheets of characters whose home is here. Storytellers and assistant storytellers always can, with a reason for the character's log.",
    "status",
  ),
  titlesOnSheets: card(
    "titlesOnSheets",
    "Titles on sheets",
    "Who gives titles to characters whose home is here. Storytellers and assistant storytellers always can, from the Roster tab or the character's Status & Titles tab.",
    "status",
  ),
  statusBans: card(
    "statusBans",
    "Status bans on clans",
    "Which clans the sects' status bans name here: who counts as a pillar clan, say, which the books change from one edition to the next. A bloodline goes with its clan. Staff can still say a ban applies to a character, or exempt one, on its Status.",
    "status",
  ),

  startingBlood: card("startingBlood", "Blood at the start of a game", "What resetting a character's Play View for the next game puts their blood back to.", "blood"),
  diablerie: card(
    "diablerie",
    "Diablerie and Lesser Generation",
    "What recording a diablerie does to a character who holds Lesser Generation or Thin Blooded. The diablerie form shows staff what this will do before they confirm.",
    "blood",
  ),
  clanWeaknesses: card(
    "clanWeaknesses",
    "Clan weaknesses",
    "Which weakness a clan plays here where Volume 2 replaced the core book's: so far only the Tremere's. Characters, creation and the rules show the one chosen. Horatio applies neither for you: staff do, as they record blood bonds.",
    "blood",
  ),
  feeding: card(
    "feeding",
    "Feeding",
    "How Horatio handles feeding between games. As the book has it, each clan needs a number of feeding actions a cycle, Herd and some traits change it, and staff answer full or half Blood for the next game. Feeding is switched on and off in the Features list.",
    "blood",
  ),
  feedingTerritories: card(
    "feedingTerritories",
    "Feeding territories",
    "Areas where only the characters the domain's Authority names may feed. Everyone in the troupe can see them, as the domain knows them. Feeding in one stands in for a feeding action, or with the Rack, it has cards of its own; feeding in another's is poaching.",
    "blood",
    (t) => t.feeding !== "off" && t.feeding_territories,
  ),

  clanNames: card(
    "clanNames",
    "Banu Haqim or Assamite",
    "What Horatio calls the clan of Haqim on every screen here: sheets, the Play View, creation, the roster, the Who's Who and the rules. Only the name shown changes; the rules and the sheets are the same either way.",
    "names",
  ),

  whosWho: card("whosWho", "Who's Who", "The troupe’s players and staff see its characters there. It shows no sect status unless you add negative status.", "whos_who"),

  playTabs: card(
    "playTabs",
    "Play View tabs",
    "The tabs players see on the Play View at games. Staff always see every tab on NPCs. Turn them all off if your players keep their sheets here but don't play from Horatio.",
    "play_view",
  ),
  nightsStatus: card(
    "nightsStatus",
    "The night's status",
    "A character with more than one source of abiding status, such as a title and its social age, carries only one into a game (MET: VTM p. 311).",
    "play_view",
  ),
  badges: card("badges", "Badges", "What the troupe's game badges print. There is always room for stickers.", "play_view"),
  throwPictures: card(
    "throwPictures",
    "Throw pictures",
    "Your troupe's own rock, paper and scissors for the Play View's Throws tab, instead of Horatio's. Once all three are here, the set can be offered to your players.",
    "play_view",
  ),

  boonLedger: card(
    "boonLedger",
    "Boons",
    `The troupe's boon ledger: the debts characters owe each other, registered with the Harpy (${BOON_PAGE}). A boon made off the record isn't tracked here, and isn't enforced. Storytellers and assistant storytellers register boons, and edit, trade, pass on, settle and void them, each with its own log.`,
    "boons",
  ),

  bloodBonds: card(
    "bloodBonds",
    "Blood bonds",
    `How Horatio keeps the blood bonds between characters (${BOND_PAGE}). A thrall's player sees their own bonds, a regnant's player only those staff mark known to them, and nobody else any. Changing the mode leaves drinks already waiting where they are.`,
    "blood_bonds",
  ),

  locationOptions: card(
    "locationOptions",
    "House options",
    "Changes to the book's Stock Locations that many troupes play. Each is on unless switched off here.",
    "locations",
  ),
  controlLimit: card(
    "controlLimit",
    "Control limit",
    "A character controls up to five locations, and one more for each dot of Retainers. Havens don't count, nor a conglomerate whose every subsidiary they control.",
    "locations",
  ),
  ownQualities: card("ownQualities", "The troupe's qualities", "Location qualities of the troupe's own, marked ★, with what a quest for one should ask for.", "locations"),
  qualityCatalogue: card(
    "qualityCatalogue",
    "The catalogue",
    "Each quality as played here, with its page and what a quest for it should ask for, by the location's rating. A standard location has up to its rating in qualities, a prestige or iconic one twice that; only an iconic one has iconic qualities, and no location more than one supernatural quality.",
    "locations",
  ),

  questRequests: card(
    "questRequests",
    "Quest requests",
    "Quests (MET: VTM Vol. II Issue 1, pp. 99-110): players ask for them, staff build them with requirements and scenarios, and Horatio keeps track as the party meets them. A request staff answer as not needed, or one withdrawn, does not count. Quests are switched on and off in the Features list, on Troupe settings.",
    "quests",
  ),

  retainerRules: card(
    "retainerRules",
    "Retainers",
    "The book has neither of these. Upkeep is taken on the Play View as each character’s night starts, at check-in or its first tap, as its own line in the night’s log. A Retainer its character can’t pay for is marked neglected and staff are told; what follows is up to you, and nothing is lost by itself. Growth goes to the NPC linked to a Retainer, for staff to spend, or is banked on the Retainer while none is. A lost Retainer pays and gains nothing.",
    "characters",
  ),

  backstoryRules: card(
    "backstoryRules",
    "Backstories",
    "Each character has one backstory, in Markdown, which only its player and this troupe's storytellers and assistant storytellers read. They read it as part of accepting the character, and can send it back with feedback.",
    "approvals",
  ),
  backstoryQuestions: card("backstoryQuestions", "Questions", "The troupe's own backstory questions, in sets, for players who answer them.", "approvals"),
  teacherRules: card(
    "teacherRules",
    "Teachers",
    "Discipline dots need a teacher by the book. Rules here ask one for other traits too. A player buying a matching trait picks a teacher from the troupe's characters who qualify, or names an NPC for you to approve, and the purchase waits on the Approvals tab.",
    "approvals",
  ),
  freeChangeRules: card(
    "freeChangeRules",
    "Free changes for new characters",
    "For a while after the troupe accepts a character, its player can lower or remove traits for their full XP back, as during creation. Each change still has to keep to the rules, and waits on the Approvals tab. Changing this applies to the characters whose free changes are open; turning it on gives them only to characters accepted from then on.",
    "approvals",
  ),
} satisfies Record<string, CardSetting>;

/** The id of a feature's row on the Features list, where it is switched on and off. */
export const switchAnchor = (key: FeatureKey) => `switch-${key.replace(/_/g, "-")}`;

/** What a Customise tab holds that its name doesn't say, for finding it by those words. */
const TAB_WORDS: Record<string, string> = {
  Setup: "Setting up the troupe, its features at a glance, and what it plays differently from the book.",
  Specialisations: "The troupe's own lists of specialisations: the areas its Influences cover, the notable people Contacts can be.",
  "News agencies": "The troupe's news agencies, each with its masthead.",
  Connectors: "How downtime results reach players: Discord, its channels, and email.",
  "Export and import": "Share the troupe's house rules, costs, wording and the rest of Customise with another troupe, as a file or from a troupe you run.",
};

/** A setting found: its name, where it is, a line on it, and the address that opens it. */
export type SettingEntry = { title: string; where: string; hint: string; to: string };

/**
 * Every setting of the troupe for someone who may open them: its running staff (storytellers
 * and the lead change them, assistant storytellers read them) and the custodian. Nobody else
 * sees any, as they see no Customise tab. Each opens where it is: a tab, a part, a dialog,
 * or a card or a feature's row, scrolled to.
 */
export function settingsIndex(troupe: TroupeOut, can: ReturnType<typeof abilities>): SettingEntry[] {
  if (!can.running) return [];
  const base = `/troupes/${troupe.id}`;
  const groups = troupeTabGroups(troupe, can);
  const tabs = groups.flatMap((g) => g.tabs.map((t) => t.to));
  const customise = groups.find((g) => g.label === "Customise")?.tabs ?? [];
  const dialogShown = (d: SettingsDialog) => tabs.includes(`${base}/${SETTINGS_DIALOGS[d].to}`);
  const dialogTitle = (d: SettingsDialog) => `${SETTINGS_DIALOGS[d].tab} settings`;
  const partLabel = (part: TroupeSettingsPart) => TROUPE_SETTINGS_PARTS.find((p) => p.part === part)!.label;

  const place = (p: CardPlace): { where: string; to: string } | null => {
    if (p === "features") return { where: "Troupe settings › Features", to: `${base}/settings` };
    if (p in SETTINGS_DIALOGS) {
      const d = p as SettingsDialog;
      return dialogShown(d) ? { where: dialogTitle(d), to: `${base}/${SETTINGS_DIALOGS[d].to}` } : null;
    }
    return { where: `Troupe settings › ${partLabel(p as TroupeSettingsPart)}`, to: `${base}/settings/${p}` };
  };

  const cards = Object.values(SETTINGS as Record<string, CardSetting>).flatMap((s) => {
    const at = place(s.in);
    if (!at || (s.shown && !s.shown(troupe))) return [];
    return [{ title: s.title, where: at.where, hint: s.about, to: `${at.to}#${s.anchor}` }];
  });
  return [
    ...customise.map((t) => ({ title: t.label, where: "Customise", hint: TAB_WORDS[t.label] ?? "", to: t.to })),
    ...TROUPE_SETTINGS_PARTS.map((p) => ({ title: p.label, where: "Troupe settings", hint: "", to: `${base}/settings/${p.part}` })),
    ...RULE_SECTIONS.map((s) => ({ title: s.label, where: "House rules", hint: "", to: `${base}/house-rules/${s.path}` })),
    ...features(troupe).map((f) => ({ title: f.name, where: "Troupe settings › Features", hint: f.adds, to: `${base}/settings#${switchAnchor(f.key)}` })),
    ...(Object.keys(SETTINGS_DIALOGS) as SettingsDialog[])
      .filter(dialogShown)
      .map((d) => ({ title: dialogTitle(d), where: `${SETTINGS_DIALOGS[d].tab} tab`, hint: "", to: `${base}/${SETTINGS_DIALOGS[d].to}#${SETTINGS_HASH}` })),
    ...cards,
  ];
}

/** Words compared as people type them: any case, and a curly apostrophe as a straight one. */
const plain = (s: string) => s.toLowerCase().replace(/[‘’]/g, "'");

/**
 * The settings that have every word typed, in their name, where they are or their line:
 * those named by what was typed first, then those whose name has every word, then the rest,
 * each in the index's order.
 */
export function findSettings(index: SettingEntry[], query: string): SettingEntry[] {
  const q = plain(query.trim());
  const words = q.split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const rank = (e: SettingEntry) => {
    const title = plain(e.title);
    if (title.startsWith(q)) return 0;
    if (words.every((w) => title.includes(w))) return 1;
    return 2;
  };
  return index
    .filter((e) => {
      const text = plain(`${e.title} ${e.where} ${e.hint}`);
      return words.every((w) => text.includes(w));
    })
    .map((e, at) => ({ e, at, rank: rank(e) }))
    .sort((a, b) => a.rank - b.rank || a.at - b.at)
    .map(({ e }) => e);
}
