/**
 * Location quests (issue #326; MET: VTM Vol. II Issue 1, pp. 118-129): the words
 * for location requests and the changes a quest makes, and what a location's
 * qualities give its controller.
 */
import type { Change } from "../../api/types";

export type RequestKind = "custom" | "acquire" | "quality" | "undermine" | "repair" | "whose";

/** What a player can ask for, as the Quests tab offers it. */
export const REQUEST_KINDS: { value: RequestKind; label: string }[] = [
  { value: "custom", label: "A quest of your own" },
  { value: "acquire", label: "Acquire a location" },
  { value: "quality", label: "Add a quality to one of your locations" },
  { value: "undermine", label: "Undermine a location" },
  { value: "repair", label: "Repair one of your locations" },
  { value: "whose", label: "Learn whose locations are whose, with Contacts" },
];

const KIND_TEXT: Record<string, string> = {
  acquire: "Acquire",
  quality: "Add a quality",
  undermine: "Undermine",
  repair: "Repair",
  whose: "Contacts",
};

/** A request's kind as a short tag, or "" for a custom quest. */
export function requestKindText(kind: string): string {
  return KIND_TEXT[kind] ?? "";
}

/** The kinds of request answered by a quest built from a location. */
export function buildsFromLocation(kind: string): boolean {
  return kind === "acquire" || kind === "quality" || kind === "undermine";
}

export const NEGATIVES = ["Damaged", "Insolvent", "Compromised", "Out of Code", "Shunned"];

export type ChangeKind = Change["kind"];

export const CHANGE_KINDS: { value: ChangeKind; label: string; verb: string }[] = [
  { value: "acquire", label: "Take control of it", verb: "Acquire" },
  { value: "quality", label: "Add a quality", verb: "Improve" },
  { value: "swap", label: "Swap a quality for another", verb: "Change" },
  { value: "upgrade", label: "Upgrade its type", verb: "Upgrade" },
  { value: "negative", label: "Impose a negative quality", verb: "Undermine" },
  { value: "infiltrate", label: "Infiltrate it", verb: "Infiltrate" },
];

export function emptyChange(kind: ChangeKind = "acquire"): Change {
  return { kind, quality: "", detail: "", swap_out: "", negative: "", secret: false, victory: "" };
}

/** The change a request asks for, as the quest builder starts it. */
export function changeFromRequest(r: { kind: string; details: Record<string, string> }): Change | null {
  const d = r.details;
  switch (r.kind) {
    case "acquire":
      return emptyChange("acquire");
    case "quality":
      return { ...emptyChange("quality"), quality: d.quality ?? "", detail: d.detail ?? "" };
    case "undermine":
      return d.negative ? { ...emptyChange("negative"), negative: d.negative } : { ...emptyChange("infiltrate"), victory: d.victory ?? "" };
    default:
      return null;
  }
}

/** A quest's name to start with: "Acquire Ruby's Bar". */
export function questName(change: Change, location: string): string {
  if (change.kind === "quality" && change.quality) return `${change.quality} for ${location}`;
  if (change.kind === "negative" && change.negative) return `${change.negative}: ${location}`;
  const verb = CHANGE_KINDS.find((k) => k.value === change.kind)?.verb ?? "";
  return `${verb} ${location}`.trim();
}

/** "Rating 2 · Historic +1". */
export function modifiersText(modifiers: { reason: string }[]): string {
  return modifiers.map((m) => m.reason).join(" · ");
}

/** What removes one level of a negative at the location's rating (pp. 127-129). */
export function removalText(negative: string, rating: number): string {
  if (negative === "Damaged") return `Resources ${rating}`;
  if (negative === "Insolvent" || negative === "Shunned") return `Elite ${rating}`;
  return `Underworld ${rating}`;
}

/**
 * One thing a location gives its controller, as the sheet shows it: "Resources 1,
 * from Ruby's Bar (Profitable)"; switched off, with ": not available this cycle",
 * and why only for staff.
 */
export function effectText(location: string, e: { quality: string; gives: string; on: boolean; off_because: string }): string {
  const text = `${e.gives}, from ${location} (${e.quality})`;
  if (e.on) return text;
  return `${text}: not available this cycle${e.off_because ? `, because of ${e.off_because}` : ""}`;
}
