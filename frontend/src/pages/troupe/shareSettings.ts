import type { SettingsDocument, ShareEditableOut, ShareReviewItemOut, ShareReviewOut } from "../../api/types";

/** One item of a document, as the client edits it. */
type Item = Record<string, unknown>;
type Sections = Record<string, Item[]>;

/** An item's place in the document, and in the ticked set: "costs:2". */
export const keyOf = (item: { section: string; index: number }) => `${item.section}:${item.index}`;

/** Items there is something to do with: new, or changing what the troupe has. */
export const tickable = (item: ShareReviewItemOut) => item.status === "new" || item.status === "changes";

const sectionsOf = (document: SettingsDocument) => document.sections as unknown as Sections;

export function itemOf(document: SettingsDocument, section: string, index: number): Item {
  return sectionsOf(document)[section]?.[index] ?? {};
}

/** The file Export downloads: "court-of-ashes-settings-2026-11-07.json", dated today where you are. */
export function fileName(troupe: string, on: Date): string {
  const slug =
    troupe
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "troupe";
  const day = [on.getFullYear(), on.getMonth() + 1, on.getDate()].map((n) => String(n).padStart(2, "0")).join("-");
  return `${slug}-settings-${day}.json`;
}

/** The document with only the chosen sections in it; the rest are left empty. */
export function withSections(document: SettingsDocument, chosen: ReadonlySet<string>): SettingsDocument {
  const sections = Object.fromEntries(Object.entries(sectionsOf(document)).map(([key, items]) => [key, chosen.has(key) ? items : []]));
  return { ...document, sections: sections as unknown as SettingsDocument["sections"] };
}

/** A field's text as it is edited: a list one entry to a line. */
export function fieldText(item: Item, field: ShareEditableOut): string {
  const value = item[field.field];
  if (field.lines) return Array.isArray(value) ? value.join("\n") : "";
  return typeof value === "string" ? value : "";
}

/** The document with one field of one item set to `text`. */
export function withField(document: SettingsDocument, section: string, index: number, field: ShareEditableOut, text: string): SettingsDocument {
  const sections = sectionsOf(document);
  const items = [...(sections[section] ?? [])];
  items[index] = { ...items[index], [field.field]: field.lines ? text.split("\n") : text };
  return { ...document, sections: { ...sections, [section]: items } as unknown as SettingsDocument["sections"] };
}

const occurrences = (text: string, find: string) => (find ? text.split(find).length - 1 : 0);

/** How often `find` comes in the ticked items' text, and in how many items. Case matters. */
export function matches(document: SettingsDocument, items: ShareReviewItemOut[], ticked: ReadonlySet<string>, find: string): { matches: number; items: number } {
  let found = 0;
  let within = 0;
  for (const item of items) {
    if (!ticked.has(keyOf(item))) continue;
    const here = item.editable.reduce((n, field) => n + occurrences(fieldText(itemOf(document, item.section, item.index), field), find), 0);
    found += here;
    if (here) within += 1;
  }
  return { matches: found, items: within };
}

/** Replace every `find` in the ticked items' text with `replacement`. */
export function replaceAll(document: SettingsDocument, items: ShareReviewItemOut[], ticked: ReadonlySet<string>, find: string, replacement: string): SettingsDocument {
  if (!find) return document;
  let next = document;
  for (const item of items) {
    if (!ticked.has(keyOf(item))) continue;
    for (const field of item.editable) {
      const text = fieldText(itemOf(next, item.section, item.index), field);
      if (text.includes(find)) next = withField(next, item.section, item.index, field, text.split(find).join(replacement));
    }
  }
  return next;
}

/** What importing the ticked items would do: "Adds 14, changes 6". */
export function counts(items: ShareReviewItemOut[], ticked: ReadonlySet<string>): { adds: number; changes: number } {
  const chosen = items.filter((i) => ticked.has(keyOf(i)));
  return { adds: chosen.filter((i) => i.status === "new").length, changes: chosen.filter((i) => i.status === "changes").length };
}

export function countsText({ adds, changes }: { adds: number; changes: number }): string {
  if (!adds && !changes) return "Nothing ticked to import";
  return `Adds ${adds}, changes ${changes}`;
}

/**
 * What to tick after a review: what there is something to do with. After a review
 * of the edited document, an item keeps the tick it had; one that has only now
 * something to do is ticked, and one with nothing to do is unticked.
 */
export function ticksFor(review: ShareReviewOut, before?: { review: ShareReviewOut; ticked: ReadonlySet<string> }): Set<string> {
  const was = new Map(before?.review.sections.flatMap((s) => s.items.map((i) => [keyOf(i), tickable(i)] as const)) ?? []);
  const ticked = new Set<string>();
  for (const item of review.sections.flatMap((s) => s.items)) {
    const key = keyOf(item);
    if (!tickable(item)) continue;
    if (before && was.get(key)) {
      if (before.ticked.has(key)) ticked.add(key);
    } else ticked.add(key);
  }
  return ticked;
}

/** The source troupe's name, when its text names it and it isn't this troupe: worth replacing. */
export function suggestion(document: SettingsDocument, items: ShareReviewItemOut[], ticked: ReadonlySet<string>, here: string): string | null {
  const source = document.troupe.trim();
  if (!source || source === here) return null;
  return matches(document, items, ticked, source).matches ? source : null;
}

/** "3 matches in 2 items". */
export function matchesText({ matches: n, items }: { matches: number; items: number }): string {
  return `${n === 1 ? "1 match" : `${n} matches`} in ${items === 1 ? "1 item" : `${items} items`}`;
}
