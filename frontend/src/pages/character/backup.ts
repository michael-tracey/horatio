import type { BackupItemOut, CharacterReviewOut, TroupeEntryOut } from "../../api/types";

/** The optional sections a backup can carry, as the server names them, in order. */
export const SECTIONS = [
  { key: "equipment", label: "Equipment" },
  { key: "retainers", label: "Retainers and Alternate Identities" },
  { key: "titles", label: "Titles and status" },
] as const;

export type Section = (typeof SECTIONS)[number]["key"];

/** The most a character's file may be, as the server takes it: its picture is in it. */
export const MAX_BYTES = 16 * 1024 * 1024;

/**
 * A character's name as a backup's file name has it, as the server makes it: accents
 * folded to their plain letter, then spaces, other letters and anything unsafe in a
 * file name dropped, case kept. "Agnes de Vries" is "AgnesdeVries"; a name with
 * nothing left is "character".
 */
export function namePart(name: string): string {
  const folded = name.normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
  return folded.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 60) || "character";
}

/** The day as YYYY-MM-DD, where you are. */
const day = (on: Date) => [on.getFullYear(), on.getMonth() + 1, on.getDate()].map((n) => String(n).padStart(2, "0")).join("-");

/** A backup's files are named for the character and the day: "AgnesdeVries-2026-11-09". */
export const fileStem = (name: string, on: Date) => `${namePart(name)}-${day(on)}`;

/** The file one character is exported as: "AgnesdeVries-2026-11-09.horatio-character.json". */
export const backupFileName = (name: string, on: Date) => `${fileStem(name, on)}.horatio-character.json`;

/** The query string for the sections chosen: "?sections=equipment&sections=titles", or "". */
export function sectionsQuery(chosen: ReadonlySet<Section>, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams();
  for (const s of SECTIONS) if (chosen.has(s.key)) params.append("sections", s.key);
  for (const [key, value] of Object.entries(extra)) params.append(key, value);
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const STATUS: Record<BackupItemOut["status"], { label: string; tone: "gold" | "mist" | "blood" }> = {
  new: { label: "New", tone: "gold" },
  differs: { label: "Differs", tone: "gold" },
  cannot: { label: "Can't import", tone: "blood" },
  info: { label: "Shown only", tone: "mist" },
};

/** How many parts come in, are held otherwise here, and are left out. */
export function reviewCounts(review: CharacterReviewOut): { new: number; differs: number; cannot: number } {
  const items = review.parts.flatMap((p) => p.items);
  return {
    new: items.filter((i) => i.status === "new").length,
    differs: items.filter((i) => i.status === "differs").length,
    cannot: items.filter((i) => i.status === "cannot").length,
  };
}

export function countsText(counts: { new: number; differs: number; cannot: number }): string {
  const parts = [`${counts.new} new`];
  if (counts.differs) parts.push(`${counts.differs} held otherwise here`);
  if (counts.cannot) parts.push(`${counts.cannot} left out`);
  return parts.join(", ");
}

/** Whether a chosen file is a zip, by its name or its first bytes' type. */
export const isZip = (file: { name: string; type: string }) => file.name.toLowerCase().endsWith(".zip") || file.type === "application/zip" || file.type === "application/x-zip-compressed";

type Outcome = TroupeEntryOut["outcome"];

/** What a troupe's import does with a character, as a badge. */
export const OUTCOMES: Record<Outcome, { label: string; tone: "gold" | "mist" | "blood" }> = {
  new: { label: "New NPC", tone: "gold" },
  given: { label: "Given", tone: "gold" },
  held: { label: "Held as an NPC", tone: "gold" },
  replaced: { label: "Replaces", tone: "gold" },
  skipped: { label: "Skipped", tone: "mist" },
  undecided: { label: "Choose", tone: "blood" },
  cannot: { label: "Can't import", tone: "blood" },
};

/** What a troupe's import does with a character, in a sentence. */
export function outcomeText(entry: Pick<TroupeEntryOut, "outcome" | "problem" | "player" | "duplicate">, canGive: boolean): string {
  switch (entry.outcome) {
    case "new":
      return "Comes in as a new NPC of the troupe.";
    case "given":
      return `Given to @${entry.player?.handle ?? "someone"}, at home here and accepted.`;
    case "held":
      return canGive ? "Held as an NPC, to give to its player later." : "Held as an NPC: a storyteller gives it to its player.";
    case "replaced":
      return `Replaces ${entry.duplicate?.name ?? "the one here"}: the NPC stays, its sheet as the file has it.`;
    case "skipped":
      return "Skipped: it doesn't come in.";
    case "undecided":
      return `${entry.duplicate ? `${entry.duplicate.name}, ${entry.duplicate.whose}, has this name` : "A character here has this name"}: skip it, replace it or add a copy.`;
    case "cannot":
      return entry.problem ?? "It can't be imported.";
  }
}

/** The import as a count of what happens: "2 new NPCs, 1 given, 1 skipped". */
export function importSummary(entries: readonly Pick<TroupeEntryOut, "outcome">[]): string {
  const count = (o: Outcome) => entries.filter((e) => e.outcome === o).length;
  const parts: string[] = [];
  const add = (n: number, one: string, many: string) => n && parts.push(`${n} ${n === 1 ? one : many}`);
  add(count("new"), "new NPC", "new NPCs");
  add(count("given"), "given to its player", "given to their players");
  add(count("held"), "held as an NPC", "held as NPCs");
  add(count("replaced"), "replacing one here", "replacing ones here");
  add(count("skipped"), "skipped", "skipped");
  add(count("undecided"), "waiting for you to choose", "waiting for you to choose");
  add(count("cannot"), "can't be imported", "can't be imported");
  return parts.join(", ") || "Nothing";
}
