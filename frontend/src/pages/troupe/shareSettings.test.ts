import { describe, expect, it } from "vitest";
import type { SettingsDocument, ShareReviewItemOut, ShareReviewOut } from "../../api/types";
import { counts, countsText, fieldText, fileName, itemOf, matches, matchesText, replaceAll, suggestion, ticksFor, withField, withSections } from "./shareSettings";

const WORDING = { field: "wording", label: "House wording", multiline: true, lines: false };
const ENTRIES = { field: "entries", label: "Entries, one per line", multiline: true, lines: true };

const DOCUMENT = {
  format: "horatio-troupe-settings",
  version: 1,
  horatio: "0.1.0",
  rule_sets: { vampire: 3 },
  troupe: "Court of Ashes",
  exported_on: "2026-11-07",
  sections: {
    xp: [{ type: "setting", key: "session_xp", value: 10 }],
    book_traits: [
      { type: "book_trait", category: "merits", name: "Iron Will", wording: "Court of Ashes: the Prince's favourites. Court of Ashes alone." },
      { type: "book_trait", category: "merits", name: "Calm Heart", wording: "Court of Ashes: rare." },
    ],
    fill_tables: [{ type: "fill_table", name: "Patrol", entries: ["Quiet in Court of Ashes", "[Fight]"] }],
  },
} as unknown as SettingsDocument;

function item(section: string, index: number, status: ShareReviewItemOut["status"], editable = [WORDING]): ShareReviewItemOut {
  return { section: section as ShareReviewItemOut["section"], index, label: `${section} ${index}`, status, reason: null, before: null, after: null, editable };
}

const ITEMS = [item("xp", 0, "changes", []), item("book_traits", 0, "new"), item("book_traits", 1, "same"), item("fill_tables", 0, "new", [ENTRIES])];
const review = (items: ShareReviewItemOut[]) =>
  ({ troupe: "Court of Ashes", warnings: [], sections: [{ key: "xp", label: "XP", group: "Troupe settings", items }] }) as unknown as ShareReviewOut;

describe("sharing settings (#521)", () => {
  it("names the file for the troupe and the day", () => {
    expect(fileName("Court of Ashes", new Date(2026, 10, 7))).toBe("court-of-ashes-settings-2026-11-07.json");
    expect(fileName("Les Enfants Perdus — Nuit", new Date(2026, 0, 2))).toBe("les-enfants-perdus-nuit-settings-2026-01-02.json");
    expect(fileName("!!!", new Date(2026, 0, 2))).toBe("troupe-settings-2026-01-02.json");
  });

  it("exports only the sections chosen", () => {
    const chosen = withSections(DOCUMENT, new Set(["xp"])).sections as unknown as Record<string, unknown[]>;
    expect(chosen.xp).toHaveLength(1);
    expect(chosen.book_traits).toEqual([]);
  });

  it("edits a field, and a list one entry a line", () => {
    const table = itemOf(DOCUMENT, "fill_tables", 0);
    expect(fieldText(table, ENTRIES)).toBe("Quiet in Court of Ashes\n[Fight]");
    const edited = withField(DOCUMENT, "fill_tables", 0, ENTRIES, "Quiet\n[Fight]\nRain");
    expect(itemOf(edited, "fill_tables", 0).entries).toEqual(["Quiet", "[Fight]", "Rain"]);
    // The document it came from is left as it was.
    expect(fieldText(table, ENTRIES)).toBe("Quiet in Court of Ashes\n[Fight]");
  });

  it("finds and replaces in the ticked items' text only", () => {
    const ticked = new Set(["book_traits:0", "fill_tables:0"]);
    expect(matches(DOCUMENT, ITEMS, ticked, "Court of Ashes")).toEqual({ matches: 3, items: 2 });
    expect(matchesText({ matches: 3, items: 2 })).toBe("3 matches in 2 items");
    expect(matchesText({ matches: 1, items: 1 })).toBe("1 match in 1 item");

    const replaced = replaceAll(DOCUMENT, ITEMS, ticked, "Court of Ashes", "Briar Court");
    expect(itemOf(replaced, "book_traits", 0).wording).toBe("Briar Court: the Prince's favourites. Briar Court alone.");
    expect(itemOf(replaced, "book_traits", 1).wording).toBe("Court of Ashes: rare.");
    expect(itemOf(replaced, "fill_tables", 0).entries).toEqual(["Quiet in Briar Court", "[Fight]"]);
    expect(matches(replaced, ITEMS, ticked, "Court of Ashes")).toEqual({ matches: 0, items: 0 });
  });

  it("suggests replacing the source troupe's name where its text has it", () => {
    expect(suggestion(DOCUMENT, ITEMS, new Set(["book_traits:0"]), "Briar Court")).toBe("Court of Ashes");
    expect(suggestion(DOCUMENT, ITEMS, new Set(["xp:0"]), "Briar Court")).toBeNull();
    expect(suggestion(DOCUMENT, ITEMS, new Set(["book_traits:0"]), "Court of Ashes")).toBeNull();
  });

  it("ticks what there is to do, and keeps choices across a review of the edits", () => {
    const first = ticksFor(review(ITEMS));
    expect([...first].sort()).toEqual(["book_traits:0", "fill_tables:0", "xp:0"]);
    expect(countsText(counts(ITEMS, first))).toBe("Adds 2, changes 1");

    // Unticked by hand, an item stays unticked; one that now differs is ticked.
    const chosen = new Set(["book_traits:0", "xp:0"]);
    const after = [item("xp", 0, "changes", []), item("book_traits", 0, "new"), item("book_traits", 1, "changes"), item("fill_tables", 0, "same", [ENTRIES])];
    expect([...ticksFor(review(after), { review: review(ITEMS), ticked: chosen })].sort()).toEqual(["book_traits:0", "book_traits:1", "xp:0"]);
    expect(countsText({ adds: 0, changes: 0 })).toBe("Nothing ticked to import");
  });
});
