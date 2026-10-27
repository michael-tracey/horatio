/**
 * The effect blocks of a house merit or flaw, as the editor shows them: each one a
 * form for one thing it does on the sheet, at a game or between games
 * (horatio.rules.house_effects on the server, which checks them and says what they do).
 */

import type { CatalogueOut, EffectBlock, EffectChoicesOut, PoolChoiceOut } from "../../api/types";

/** What a block does, as the editor offers it. Prices cover three engine kinds. */
export type BlockType =
  | "free"
  | "picks"
  | "raise"
  | "price"
  | "in_clan"
  | "health"
  | "requires"
  | "forbids"
  | "pool"
  | "switch"
  | "uses"
  | "downtime"
  | "feeding";

export const BLOCK_TYPES: { type: BlockType; label: string }[] = [
  { type: "free", label: "Gives free dots" },
  { type: "picks", label: "The player picks several, each with free dots" },
  { type: "raise", label: "Raises a maximum" },
  { type: "price", label: "Changes an XP price" },
  { type: "in_clan", label: "Adds an in-clan discipline from a list" },
  { type: "health", label: "Adds or takes away health levels" },
  { type: "requires", label: "Requires…" },
  { type: "forbids", label: "Not with…" },
  { type: "pool", label: "Pool bonus, always on" },
  { type: "switch", label: "Pool changes while switched on in play" },
  { type: "uses", label: "Uses per game" },
  { type: "downtime", label: "Extra downtime actions of a kind" },
  { type: "feeding", label: "Changes feeding between games" },
];

export const PRICE_KINDS: { kind: EffectBlock["kind"]; label: string }[] = [
  { kind: "cost_percent", label: "A percent of the usual price" },
  { kind: "price_in_clan", label: "Priced as in-clan" },
  { kind: "price_out_of_clan", label: "Priced as out-of-clan" },
];

export const STRENGTHS: { strength: EffectBlock["strength"]; label: string }[] = [
  { strength: "refuse", label: "Refused otherwise" },
  { strength: "complete", label: "By the end of creation" },
  { strength: "review", label: "Otherwise staff approve it" },
  { strength: "note", label: "Only a note on the sheet" },
];

export const EXTRA_IN_CLAN = "extra_in_clan_disciplines";
export const HEALTH = "health_levels";

export function typeOf(block: EffectBlock): BlockType {
  switch (block.kind) {
    case "free_up_to":
      return "free";
    case "free_choices":
      return "picks";
    case "raise_max":
      return "raise";
    case "cost_percent":
    case "price_in_clan":
    case "price_out_of_clan":
      return "price";
    case "extra_in_clan":
      return "in_clan";
    case "add":
      return "health";
    case "pool_bonus":
      return "pool";
    case "uses_per_game":
      return "uses";
    case "downtime_action":
      return "downtime";
    default:
      return block.kind;
  }
}

const BLANK: EffectBlock = {
  kind: "free_up_to",
  category: "",
  names: [],
  amount: 0,
  count: 1,
  detail: "",
  test: "trait",
  name: "",
  rating: null,
  strength: "refuse",
  pools: [],
  when: "",
  changes: [],
  note: "",
  action_kind: "",
  herd_factor: 1,
  always_half: false,
};

/** A new block of the type, with sensible starting values. */
export function newBlock(type: BlockType): EffectBlock {
  switch (type) {
    case "free":
      return { ...BLANK, kind: "free_up_to", category: "backgrounds", amount: 1 };
    case "picks":
      return { ...BLANK, kind: "free_choices", category: "backgrounds", amount: 1, count: 1 };
    case "raise":
      return { ...BLANK, kind: "raise_max", category: "skills", amount: 1 };
    case "price":
      return { ...BLANK, kind: "cost_percent", category: "skills", amount: 50 };
    case "in_clan":
      return { ...BLANK, kind: "extra_in_clan" };
    case "health":
      return { ...BLANK, kind: "add", category: HEALTH, amount: 1 };
    case "requires":
    case "forbids":
      return { ...BLANK, kind: type, test: "trait", category: "backgrounds", rating: 1 };
    case "pool":
      return { ...BLANK, kind: "pool_bonus", amount: 1 };
    case "switch":
      return { ...BLANK, kind: "switch", changes: [{ pool: "", amount: 1 }] };
    case "uses":
      return { ...BLANK, kind: "uses_per_game", amount: 1 };
    case "downtime":
      return { ...BLANK, kind: "downtime_action", action_kind: "general", amount: 1 };
    case "feeding":
      return { ...BLANK, kind: "feeding", amount: -1 };
  }
}

/** The pools a block can change: an always-on bonus, or a switch, as the server lists them. */
export function poolChoices(choices: EffectChoicesOut | undefined, type: BlockType): PoolChoiceOut[] {
  return (choices?.pools ?? []).filter((p) => (type === "switch" ? p.switch : p.always));
}

/** The pools in their groups, for a picker: [group, pools] in the server's order. */
export function poolGroups(pools: PoolChoiceOut[]): [string, PoolChoiceOut[]][] {
  const groups = new Map<string, PoolChoiceOut[]>();
  for (const p of pools) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups];
}

/** "+2", "−2". */
export function signed(n: number): string {
  return n < 0 ? `−${-n}` : `+${n}`;
}

/** The kinds of trait a block can give dots in, raise or price: rated ones bought dot by dot. */
export function dotCategories(catalogue: CatalogueOut, type: BlockType): CatalogueOut["categories"] {
  return catalogue.categories.filter(
    (c) =>
      c.rated &&
      !c.derived &&
      !c.specializes &&
      c.key !== EXTRA_IN_CLAN &&
      (type === "free" || (c.key !== "merits" && c.key !== "flaws")) &&
      catalogue.traits.some((t) => t.category === c.key),
  );
}

/** The kinds of trait a check can ask for. */
export function checkCategories(catalogue: CatalogueOut): CatalogueOut["categories"] {
  return catalogue.categories.filter((c) => !c.derived && !c.specializes && !["clan", "sect"].includes(c.key) && catalogue.traits.some((t) => t.category === c.key));
}

/** The names a block can list in its category: the catalogue's, but never the merit itself. */
export function traitNames(catalogue: CatalogueOut, category: string, self?: { category: string; name: string }): string[] {
  return catalogue.traits
    .filter((t) => t.category === category && !(self && t.category === self.category && t.name === self.name))
    .map((t) => t.name);
}

/** Clans and their bloodlines go together: "Brujah" for "Brujah: True Brujah". */
export function clanFamilies(catalogue: CatalogueOut): string[] {
  return [...new Set(catalogue.traits.filter((t) => t.category === "clan").map((t) => t.name.split(":")[0]!.trim()))].sort();
}

export function sects(catalogue: CatalogueOut): string[] {
  return traitNames(catalogue, "sect");
}

/** A trait in a check has a rating to reach when it is bought dot by dot. */
export function hasRating(catalogue: CatalogueOut, category: string, name: string): boolean {
  const c = catalogue.categories.find((x) => x.key === category);
  const t = catalogue.traits.find((x) => x.category === category && x.name === name);
  return Boolean(c?.rated) && t?.fixed_rating == null;
}

/** Turn a block into another type, keeping what still fits. */
export function retype(block: EffectBlock, type: BlockType): EffectBlock {
  if (typeOf(block) === type) return block;
  const fresh = newBlock(type);
  const keepsTraits = ["free", "picks", "raise", "price"].includes(type) && ["free", "picks", "raise", "price"].includes(typeOf(block));
  return keepsTraits ? { ...fresh, category: block.category, names: block.names ?? [] } : fresh;
}
