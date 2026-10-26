/**
 * A ghoul's Embrace (MET: VTM pp. 297–299): what the staff's form holds, and the
 * choices it sends. What each step does and costs is the server's to say, in its plan.
 */

import type { EmbraceChoicesIn, EmbracePlanOut, EmbraceStepOut, SireChoiceOut } from "../../api/types";

/** The most lost discipline dots that can be bought back (p. 298). */
export const BUY_BACK_DOTS = 2;

/** The sire as the form holds it: a vampire in Horatio, or one named, with its clan and generation. */
export type SireDraft = { kind: "linked"; choice: SireChoiceOut | null } | { kind: "named"; name: string; clan: string; generation: number | null };

export type EmbraceDraft = {
  sire: SireDraft;
  /** Whether the sire was the domitor, where staff say; null works it out. */
  sireIsDomitor: boolean | null;
  /** The sire's clan and rarity merits; null takes the plan's suggestion. */
  clanMerits: string[] | null;
  twoDots: string | null;
  caitiffThree: string[];
  /** Merits and flaws to take off, as "category/name/detail". */
  remove: string[];
  /** Each lost discipline bought back to a rating. */
  buyBack: Record<string, number>;
  intoDebt: boolean;
  weakness: string;
};

export const newDraft = (): EmbraceDraft => ({
  sire: { kind: "linked", choice: null },
  sireIsDomitor: null,
  clanMerits: null,
  twoDots: null,
  caitiffThree: ["", "", ""],
  remove: [],
  buyBack: {},
  intoDebt: false,
  weakness: "",
});

/** The key a merit or flaw to take off is held by, and back again. */
export const removeKey = (t: { category: string; name: string; detail: string }) => `${t.category}/${t.name}/${t.detail}`;

export function fromRemoveKey(key: string): { category: "merits" | "flaws"; name: string; detail: string } {
  const [category = "merits", name = "", ...detail] = key.split("/");
  return { category: category === "flaws" ? "flaws" : "merits", name, detail: detail.join("/") };
}

/** What is missing before the sire can be planned for, or null. */
export function sireMissing(sire: SireDraft): string | null {
  if (sire.kind === "linked") return sire.choice ? (sire.choice.generation == null ? `${sire.choice.name}'s sheet gives no generation: name the sire instead.` : null) : "Choose the sire.";
  if (!sire.name.trim()) return "Give the sire's name.";
  if (!sire.clan) return "Choose the sire's clan.";
  if (!sire.generation) return "Give the sire's generation.";
  return null;
}

/** The choices the server plans and makes the Embrace by. */
export function choicesBody(draft: EmbraceDraft): EmbraceChoicesIn {
  const sire =
    draft.sire.kind === "linked"
      ? { character_id: draft.sire.choice?.character_id ?? null, name: "", clan: "", generation: null }
      : { character_id: null, name: draft.sire.name.trim(), clan: draft.sire.clan, generation: draft.sire.generation };
  return {
    sire,
    sire_is_domitor: draft.sireIsDomitor,
    clan_merits: draft.clanMerits,
    two_dots: draft.twoDots,
    caitiff_three: draft.caitiffThree.filter(Boolean),
    remove: draft.remove.map(fromRemoveKey),
    buy_back: Object.entries(draft.buyBack)
      .filter(([, rating]) => rating > 0)
      .map(([name, rating]) => ({ name, rating })),
    buy_back_into_debt: draft.intoDebt,
    weakness: draft.weakness,
  };
}

/** How many lost dots the draft buys back, over what the new vampire starts with. */
export function dotsBoughtBack(buyBack: Record<string, number>, plan: Pick<EmbracePlanOut, "disciplines">): number {
  const starting = new Map(plan.disciplines.map((d) => [d.name, d.rating]));
  return Object.entries(buyBack).reduce((n, [name, rating]) => n + Math.max(0, rating - (starting.get(name) ?? 0)), 0);
}

/** Each step with the XP the character has after it, from what it had before. */
export function running(plan: Pick<EmbracePlanOut, "balance_before" | "steps">): { step: EmbraceStepOut; after: number }[] {
  let balance = plan.balance_before;
  return plan.steps.map((step) => ({ step, after: (balance += step.xp) }));
}

/** "11th", "12th", "21st". */
export function ordinal(n: number): string {
  const suffix = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

/** XP as the form shows it: "+2 XP", "−12 XP", or nothing for none. */
export function xpText(xp: number): string {
  if (xp === 0) return "";
  return xp > 0 ? `+${xp} XP` : `−${-xp} XP`;
}

/** A balance as the form shows it: unspent XP, or the debt it comes to. */
export function balanceText(balance: number): string {
  return balance < 0 ? `${-balance} XP owed` : `${balance} XP`;
}
