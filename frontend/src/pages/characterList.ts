/**
 * The characters page's list (issue #368): where each character stands, and
 * what waits for its player.
 */
import type { CharacterListOut } from "../api/types";
import type { Dates } from "../dates";
import { newResults } from "./character/resultsSeen";

export type Tone = "mist" | "gold" | "blood";
export type Note = { label: string; tone: Tone };

/**
 * Where a character stands: retired, still being made, waiting for a troupe to
 * accept it, at home in one, or finished with no home yet. Gold asks the player
 * to do something; mist does not.
 */
export function standing(c: CharacterListOut): Note[] {
  if (c.status === "retired") return [{ label: "Retired", tone: "mist" }];
  if (!c.creation_complete) return [{ label: "In creation", tone: "gold" }, ...builtTo(c)];
  const notes: Note[] = [];
  if (c.home_troupe_name) notes.push({ label: `Home: ${c.home_troupe_name}`, tone: "mist" });
  if (c.asking_troupe_name) notes.push({ label: `Waiting for ${c.asking_troupe_name}`, tone: "mist" });
  return [...(notes.length ? notes : [{ label: "No home troupe yet", tone: "gold" as const }]), ...builtTo(c)];
}

/**
 * Whose rules a character with no home troupe is built to (issue #569): the troupe it
 * is built for, or the book's. Nothing when it is asking that troupe already, which
 * "Waiting for" says.
 */
function builtTo(c: CharacterListOut): Note[] {
  if (c.home_troupe_id || (c.building_troupe_id && c.building_troupe_id === c.asking_troupe_id)) return [];
  const label = c.building_troupe_name ? `Built to ${c.building_troupe_name}'s rules` : "Built to the book's rules";
  return [{ label, tone: "mist" }];
}

/**
 * What waits for the player: a downtime to submit, and results they haven't
 * opened on this device (as the character's Results tab counts them).
 */
export function waiting(c: CharacterListOut, seen: string | null, dates: Dates, now: Date = new Date()): Note[] {
  if (c.status === "retired" || !c.creation_complete) return [];
  const notes: Note[] = [];
  if (c.downtime_due)
    notes.push({
      label: new Date(c.downtime_due) <= now ? "Downtime overdue" : `Downtime due ${dates.due(c.downtime_due, now)}`,
      tone: "blood",
    });
  if (newResults(c.delivered, seen, now.getTime()) > 0) notes.push({ label: "New results", tone: "gold" });
  return notes;
}
