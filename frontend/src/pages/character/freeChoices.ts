/**
 * Merits that give free traits the player chooses (Ventrue Royalty and five
 * more): the rules for filling in the choices, apart from how they are drawn.
 * A merit offers one or more grants; the picks for all of them are kept together
 * and sent as one list.
 */

import type { FreeChoicesOut, FreeOptionOut, FreePickIn } from "../../api/types";

export type FreePick = FreePickIn;

/** What a grant asks of the player, in a line. */
export function rule(offer: FreeChoicesOut): string {
  if (offer.places) return `Place ${list(offer.places)} dots, each in a different one.`;
  if (offer.points != null) return `Up to ${offer.points} points of merits.`;
  if (offer.count === 1) return "Choose one.";
  return `Choose ${offer.count}.`;
}

function list(numbers: number[]): string {
  return numbers.length < 2 ? numbers.join("") : `${numbers.slice(0, -1).join(", ")} and ${numbers[numbers.length - 1]}`;
}

/** The heading for a grant: "Choose your free merits". */
export function heading(offer: FreeChoicesOut): string {
  return `Choose your free ${offer.category_name.toLowerCase()}`;
}

export const picksOf = (picks: FreePick[], offer: FreeChoicesOut) => picks.filter((p) => p.grant === offer.grant);

const without = (picks: FreePick[], offer: FreeChoicesOut, keep: (p: FreePick) => boolean) =>
  picks.filter((p) => p.grant !== offer.grant || keep(p));

/** The pick placed with this amount, if any. */
export const placed = (picks: FreePick[], offer: FreeChoicesOut, amount: number) => picksOf(picks, offer).find((p) => p.amount === amount);

/** Place `amount` dots on a trait (or on none): a trait already placed with another amount moves. */
export function place(picks: FreePick[], offer: FreeChoicesOut, amount: number, name: string): FreePick[] {
  const rest = without(picks, offer, (p) => p.amount !== amount && p.name !== name);
  return name ? [...rest, { grant: offer.grant, name, detail: "", amount }] : rest;
}

/** The pick in slot `i` of a grant that chooses a few, in the order chosen. */
export const slot = (picks: FreePick[], offer: FreeChoicesOut, i: number): FreePick | undefined => picksOf(picks, offer)[i];

/** Fill slot `i` with a trait (or empty it), keeping the other slots where they are. */
export function fill(picks: FreePick[], offer: FreeChoicesOut, i: number, name: string, detail = ""): FreePick[] {
  const mine = picksOf(picks, offer);
  const next = [...mine];
  if (name) next[i] = { grant: offer.grant, name, detail, amount: 0 };
  else next.splice(i, 1);
  return [...picks.filter((p) => p.grant !== offer.grant), ...next.filter(Boolean)];
}

/** Say the words for a pick that needs them ("Custom": Latin). */
export function describePick(pick: Pick<FreePick, "name" | "detail" | "amount">): string {
  const text = pick.detail ? (pick.name === "Custom" ? pick.detail : `${pick.name}: ${pick.detail}`) : pick.name;
  return pick.amount ? `${text} ${pick.amount}` : text;
}

export const optionOf = (offer: FreeChoicesOut, name: string): FreeOptionOut | undefined => offer.options.find((o) => o.name === name);

/** The points of merits picked so far. */
export function pointsUsed(picks: FreePick[], offer: FreeChoicesOut): number {
  return picksOf(picks, offer).reduce((sum, p) => sum + (optionOf(offer, p.name)?.rating ?? 0), 0);
}

/** Toggle a merit in a grant that gives a budget of points; `detail` is its field, if it has one. */
export function toggle(picks: FreePick[], offer: FreeChoicesOut, name: string, on: boolean): FreePick[] {
  const rest = without(picks, offer, (p) => p.name !== name);
  return on ? [...rest, { grant: offer.grant, name, detail: "", amount: 0 }] : rest;
}

export function setDetail(picks: FreePick[], offer: FreeChoicesOut, name: string, from: string, detail: string): FreePick[] {
  return picks.map((p) => (p.grant === offer.grant && p.name === name && p.detail === from ? { ...p, detail } : p));
}

/** Whether every pick that needs words has them, so the choices can be saved. */
export function sayable(picks: FreePick[], offers: FreeChoicesOut[]): boolean {
  return picks.every((p) => {
    const offer = offers.find((o) => o.grant === p.grant);
    return !offer || !optionOf(offer, p.name)?.needs_detail || p.detail.trim() !== "";
  });
}

/** The picks as sent: words trimmed. */
export const toSend = (picks: FreePick[]): FreePick[] => picks.map((p) => ({ ...p, detail: p.detail.trim() }));

/** What the cart shows for the picks made with a merit: "Resources 4, Herd 3". */
export function summary(offers: FreeChoicesOut[], picks: FreePick[]): string {
  return picks
    .filter((p) => offers.some((o) => o.grant === p.grant))
    .map(describePick)
    .join(", ");
}
