import type { WhosWhoEntry, WhosWhoOut } from "../../api/types";

/** What the Who's Who is narrowed to: a search, and a clan and sect ("" for any). */
export type WhosWhoFilter = { query: string; clan: string; sect: string };

export const NO_FILTER: WhosWhoFilter = { query: "", clan: "", sect: "" };

export type Section = {
  /** For the jump list, and the link to it. */
  id: string;
  title: string;
  /** "court" lists titles; "other" says who speaks for the clan; "departed" why it left. */
  kind: "court" | "clan" | "other" | "departed";
  entries: WhosWhoEntry[];
};

/** A clan without its bloodline: "Brujah" for "Brujah: True Brujah". */
export function clanFamily(clan: string | null): string | null {
  return clan ? (clan.split(":")[0] ?? clan).trim() : null;
}

/** "Brujah (True Brujah)", or the clan alone; "No clan yet" without one. */
export function clanText(clan: string | null): string {
  if (!clan) return "No clan yet";
  const [family, bloodline] = clan.split(":").map((s) => s.trim());
  return bloodline ? `${family} (${bloodline})` : clan;
}

/** Whether the entry is found by the search: its name, its player's, or a title it holds. */
export function matches(entry: WhosWhoEntry, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [entry.name, entry.player_name ?? "", ...entry.titles].some((s) => s.toLowerCase().includes(q));
}

function shown(entry: WhosWhoEntry, filter: WhosWhoFilter): boolean {
  return (
    matches(entry, filter.query) && (!filter.clan || clanFamily(entry.clan) === filter.clan) && (!filter.sect || (entry.sect ?? "") === filter.sect)
  );
}

/** The anchor of a clan's section. */
export function clanId(clan: string | null): string {
  return `clan-${(clan ?? "none").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/**
 * The Who's Who's sections, in order, as far as the filter lets each entry show:
 * the court, each seated clan, Other and No longer with us. A section left empty
 * is left out.
 */
export function sections(data: WhosWhoOut, filter: WhosWhoFilter = NO_FILTER): Section[] {
  const byId = new Map(data.entries.map((e) => [e.character_id, e]));
  const pick = (ids: string[]) => ids.map((id) => byId.get(id)).filter((e): e is WhosWhoEntry => !!e && shown(e, filter));
  const all: Section[] = [
    { id: "court", title: "Court", kind: "court", entries: pick(data.court) },
    ...data.clans.map((c): Section => ({ id: clanId(c.clan), title: c.clan ?? "No clan yet", kind: "clan", entries: pick(c.character_ids) })),
    { id: "other", title: "Other", kind: "other", entries: pick(data.other) },
    { id: "departed", title: "No longer with us", kind: "departed", entries: pick(data.departed) },
  ];
  return all.filter((s) => s.entries.length > 0);
}

/** The clans and sects there are to filter by, each once, by name. */
export function filterChoices(data: WhosWhoOut): { clans: string[]; sects: string[] } {
  const unique = (values: (string | null)[]) => [...new Set(values.filter((v): v is string => !!v))].sort();
  return { clans: unique(data.entries.map((e) => clanFamily(e.clan))), sects: unique(data.entries.map((e) => e.sect)) };
}
