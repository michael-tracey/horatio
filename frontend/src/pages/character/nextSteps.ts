/**
 * Next for this character (issue #1051), from GET /characters/next and
 * /characters/{id}/next: what needs its player, what waits on staff and since when,
 * and what is coming up. The card at the top of a character's page and its line on
 * the Characters page read the same steps, so they never disagree.
 */
import type { NextStepOut } from "../../api/types";
import type { Dates } from "../../dates";
import { isNew } from "./resultsSeen";

export type Step = NextStepOut;
export type Who = Step["who"];

/** The three groups, in order, with their headings. */
export const GROUPS: { who: Who; heading: string }[] = [
  { who: "player", heading: "For you" },
  { who: "staff", heading: "Waiting on staff" },
  { who: "coming", heading: "Coming up" },
];

/**
 * The steps to show. New results only while they are new to the player on this
 * device, as the Results tab counts them (resultsSeen): Horatio keeps no record of
 * which they have opened, so the server says when the newest came.
 */
export function shown(steps: Step[] | undefined, seen: string | null, now: number = Date.now()): Step[] {
  return (steps ?? []).filter((s) => s.kind !== "results" || (!!s.since && isNew(s.since, seen, now)));
}

/** A step's words, with its time where it has one: "Downtime due Sat 7 Nov, 11:59 pm", "Next game Sat 14 Nov, 7 pm EST". */
export function stepText(s: Step, dates: Dates, now: Date = new Date()): string {
  if (s.kind === "downtime_due" && s.at) return new Date(s.at) <= now ? "Downtime overdue" : `Downtime due ${dates.due(s.at, now)}`;
  if (s.kind === "next_game" && s.at) return `Next game ${dates.gameStart(s.at, now)}`;
  if (s.kind === "free_changes" && s.at) return `Free changes until ${dates.dueDay(s.at, now)}`;
  return s.label;
}

/** Since when a step has waited on staff, "since Fri 20 Nov"; null for any other. */
export function sinceText(s: Step, dates: Dates, now: Date = new Date()): string | null {
  return s.who === "staff" && s.since ? `since ${dates.dueDay(s.since, now)}` : null;
}

/** Gold for what the player does, red for a downtime due, mist for the rest. */
export function toneOf(s: Step): string {
  if (s.kind === "downtime_due") return "text-blood-bright";
  return s.who === "player" ? "text-gold" : "text-parchment";
}
