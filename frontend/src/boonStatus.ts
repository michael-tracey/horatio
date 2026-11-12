/**
 * Status the book ties to boons (#694; MET: VTM p. 316): a Disgraced creditor's boons
 * need not be repaid; an apology and a boon put a slip right, a minor boon under
 * Warned and a major one under Disgraced; spending Praised claims help from an
 * Accepted member of the sect not already in the character's debt.
 */
import { listed } from "./pages/character/creation/notices";

export const STATUS_BOON_PAGE = "MET: VTM p. 316";

/** The note beside a boon whose creditor holds Disgraced. */
export function disgracedText(creditor: string): string {
  return `Need not be repaid while ${creditor} is Disgraced (p. 316).`;
}

/** The boon an apology owes for a slip under a status, or undefined for any other status. */
export function apologyFor(status: string): { kind: "minor" | "major"; words: string } | undefined {
  if (status === "Warned") return { kind: "minor", words: "a minor boon" };
  if (status === "Disgraced") return { kind: "major", words: "a major boon" };
  return undefined;
}

/** Whom spending Praised can claim help from, in a sentence. */
export function claimsText(names: string[], sect: string | null, troupe: string): string {
  if (!sect) return "Only a character a sect has Accepted can claim help with Praised.";
  if (names.length === 0) return `Everyone of the ${sect} in ${troupe} is already in your debt.`;
  return `Not in your debt: ${listed(names)}.`;
}
