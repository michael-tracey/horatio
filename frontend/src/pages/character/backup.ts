import type { BackupItemOut, CharacterReviewOut } from "../../api/types";

/** The optional sections a backup can carry, as the server names them, in order. */
export const SECTIONS = [
  { key: "equipment", label: "Equipment" },
  { key: "retainers", label: "Retainers and Alternate Identities" },
  { key: "titles", label: "Titles and status" },
] as const;

export type Section = (typeof SECTIONS)[number]["key"];

/** The most a character's file may be, as the server takes it: its picture is in it. */
export const MAX_BYTES = 16 * 1024 * 1024;

/** A name fit for a file, as the server makes it: "Agnes de Vries" is "agnes-de-vries". */
export function slug(name: string): string {
  const found = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/g, "");
  return found || "character";
}

/** The file one character is exported as: "agnes.horatio-character.json". */
export const backupFileName = (name: string) => `${slug(name)}.horatio-character.json`;

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
