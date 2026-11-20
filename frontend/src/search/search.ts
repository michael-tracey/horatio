import type { components } from "../api/schema";

/**
 * Searching everything from the top bar (#1046). The server finds what lives in the
 * database, as far as the person may see it (horatio.search), kind by kind; what the
 * app already holds is searched here, by the local sources below: the manual now, and
 * next a troupe's settings by their labels (#1047), which add a source to
 * `LOCAL_SOURCES` and nothing else.
 */

export type SearchHit = components["schemas"]["HitOut"];
export type SearchGroup = components["schemas"]["GroupOut"];

/** Where the person is searching from: the troupe whose pages they are on, if any. */
export type SearchPlace = { troupeId: string | null };

/** A kind searched in the browser, from what the app holds. Its hits come in its own group, after the server's. */
export type LocalSource = {
  kind: string;
  label: string;
  /** At most `LIMIT + 1` hits, best first: one more than shown says there are more. */
  find: (query: string, place: SearchPlace) => Promise<SearchHit[]>;
};

/** Hits shown of each kind, as the server shows them. */
export const LIMIT = 5;
/** Fewer letters than this find nothing. */
export const SHORTEST = 2;

/** The manual, loaded only once someone searches (it is the Help pages' own chunk). */
export const manualSource: LocalSource = {
  kind: "manual",
  label: "Help",
  async find(query) {
    const [{ MANUAL }, { search }] = await Promise.all([import("../manual/content"), import("../manual/manual")]);
    return search(MANUAL, query, LIMIT + 1).map((hit) => ({
      id: hit.to,
      title: hit.section.heading ? `${hit.section.pageTitle} › ${hit.section.heading}` : hit.section.pageTitle,
      detail: hit.snippet.map((part) => part.text).join(""),
      to: hit.to,
      troupe: null,
      troupe_id: null,
    }));
  },
};

export const LOCAL_SOURCES: LocalSource[] = [manualSource];

/** Each local source's hits as a group of its own, those with none left out. */
export async function searchHere(query: string, place: SearchPlace, sources: LocalSource[] = LOCAL_SOURCES): Promise<SearchGroup[]> {
  const words = query.trim();
  if (words.length < SHORTEST) return [];
  const found = await Promise.all(sources.map(async (s) => ({ source: s, hits: await s.find(words, place) })));
  return found
    .filter((f) => f.hits.length > 0)
    .map(({ source, hits }) => ({ kind: source.kind, label: source.label, hits: hits.slice(0, LIMIT), more: hits.length > LIMIT }));
}

/** The troupe whose pages these are: `/troupes/:id/...` and the Play View's `/play/troupes/:id/...`. */
export function troupeOf(pathname: string): string | null {
  return /^\/(?:play\/)?troupes\/([0-9a-f-]{36})(?:\/|$)/.exec(pathname)?.[1] ?? null;
}

/** Whether a key press is the shortcut that opens the search: `/` outside a text box, or Ctrl+K (⌘K on a Mac). */
export function isSearchShortcut(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "target">): boolean {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") return true;
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return false;
  const el = e.target as HTMLElement | null;
  return !(el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)));
}
