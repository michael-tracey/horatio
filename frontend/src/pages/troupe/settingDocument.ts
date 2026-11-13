import type { GeneratedOut, RarityChangeOut } from "../../api/types";

const RARITIES = [
  { rarity: "common", label: "Common clans" },
  { rarity: "uncommon", label: "Uncommon clans" },
  { rarity: "rare", label: "Rare clans" },
  { rarity: "restricted", label: "Restricted clans" },
] as const;

/** The setting and its factions, as the book's crossover rules have them (MET: VTM p. 334). */
export function settingText(g: Pick<GeneratedOut, "sects" | "setting">): string {
  if (g.setting) return `${g.setting}. Every character is built by the ${g.setting} setting's costs and clan rarities.`;
  if (g.sects.length === 0) return "Any sect. Each character is built by its own sect's setting: its costs and clan rarities.";
  const [last, ...rest] = [...g.sects].reverse();
  const factions = rest.length ? `${rest.reverse().join(", ")} and ${last}` : last;
  return `Factions: ${factions}. Each character is built by its own sect's setting, its costs and clan rarities, and plays by this chronicle's mechanics (p. 334).`;
}

/**
 * The clans rated differently here, by their rarity here: common, uncommon and rare
 * always, as the book's examples list them ("Settings default" where none changes),
 * and restricted only when a clan is.
 */
export function rarityTiers(changes: RarityChangeOut[]): { rarity: string; label: string; changes: RarityChangeOut[] }[] {
  return RARITIES.map((r) => ({ ...r, changes: changes.filter((c) => c.rarity === r.rarity) })).filter(
    (t) => t.rarity !== "restricted" || t.changes.length > 0,
  );
}

/** What a new character starts with, as the book's examples put it ("Initial XP is 100 XP"). */
export function initialXpText(g: Pick<GeneratedOut, "initial_xp" | "incentive">): string {
  const i = g.incentive;
  if (!i) return `Initial XP is ${g.initial_xp} XP.`;
  return `Initial XP is the base award (${i.base} XP) + the New Character Incentive (25% of the ${i.earned} XP a character could have earned in the chronicle, ${i.bonus} XP): ${i.total} XP (p. 349).`;
}
