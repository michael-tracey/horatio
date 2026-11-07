import type { components } from "../../api/schema";

export type YorickImport = components["schemas"]["YorickImportOut"];
export type YorickReport = components["schemas"]["ReportOut"];
export type ReportCharacter = components["schemas"]["ReportCharacterOut"];
export type Unmatched = components["schemas"]["UnmatchedOut"];

/** One printed line that matched nothing, with every character it was printed for. */
export type UnmatchedLine = Unmatched & { characters: string[] };

/**
 * The printed lines that matched nothing, each once however many characters
 * printed it, the most printed first: one name given in the troupe's table
 * matches them all. Lines left for staff by hand are split off.
 */
export function unmatchedLines(characters: ReportCharacter[], byHand: string[]): { waiting: UnmatchedLine[]; handed: UnmatchedLine[] } {
  const lines = new Map<string, UnmatchedLine>();
  for (const c of characters) {
    for (const u of c.unmatched) {
      const found = lines.get(u.source);
      if (found) {
        if (!found.characters.includes(c.name)) found.characters.push(c.name);
      } else lines.set(u.source, { ...u, characters: [c.name] });
    }
  }
  const all = [...lines.values()].sort((a, b) => b.characters.length - a.characters.length || a.source.localeCompare(b.source));
  const handed = new Set(byHand);
  return { waiting: all.filter((l) => !handed.has(l.source)), handed: all.filter((l) => handed.has(l.source)) };
}

/** "Influence area", from what the line is ("influence_underworld_specializations"). */
export function categoryWord(category: string): string {
  const words: Record<string, string> = {
    backgrounds: "background",
    disciplines: "discipline or path",
    techniques: "technique",
    elder_disciplines: "elder power",
    luminary_disciplines: "luminary power",
    rituals: "ritual",
    sabbat_rituals: "Sabbat ritus",
    merits: "merit",
    flaws: "flaw",
    skills: "skill",
    paths: "Morality",
    clan: "clan",
    sect: "sect",
    faction: "faction",
    archetype: "archetype",
    haven_specializations: "Haven quality",
    influence_elite_specializations: "Influence area",
    influence_underworld_specializations: "Influence area",
    lore_specializations: "Lore",
    linguistics_specializations: "language",
    academics_specializations: "Academics field",
    drive_specializations: "kind of vehicle",
    contacts_specializations: "Contact",
    allies_specializations: "Ally",
  };
  return words[category] ?? category.replaceAll("_", " ");
}

export const OUTCOMES: Record<ReportCharacter["outcome"], { dry: string; done: string; tone: "mist" | "gold" | "blood" }> = {
  made: { dry: "To be made", done: "Made", tone: "gold" },
  updated: { dry: "To be updated", done: "Updated", tone: "gold" },
  overwritten: { dry: "To overwrite", done: "Overwrote", tone: "gold" },
  skipped: { dry: "Skipped", done: "Skipped", tone: "mist" },
  undecided: { dry: "Needs a choice", done: "Not imported", tone: "blood" },
  failed: { dry: "Fails", done: "Failed", tone: "blood" },
};
