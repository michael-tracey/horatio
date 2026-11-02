import { describe, expect, it } from "vitest";
import { keepUnchanged, toDoc, toMarkdown } from "./backstoryMarkdown";
import { parseBlocks } from "./markdown";

const roundTrip = (md: string) => toMarkdown(toDoc(md));

/** Markdown as a backstory holds it, built from the troupe's questions with the player's own words around it. */
const BUILT = [
  "# Agnes",
  "",
  "My own opening, with **bold**, *italic* and a [link](https://example.com).",
  "",
  "<!-- questions:0196f2a4-1111-7000-8000-000000000001 -->",
  "",
  "# The Pitch",
  "",
  "## Where were you born?",
  "",
  "Dublin, in 1890",
  "on a wet night.",
  "",
  "## My sire",
  "",
  "Lord Ashe *was* cruel.",
  "",
  "<!-- /questions:0196f2a4-1111-7000-8000-000000000001 -->",
  "",
].join("\n");

const SAMPLES: Record<string, string> = {
  "headings and paragraphs": "# One\n\n## Two\n\n###### Six\n\nA paragraph\nwith a line break.",
  emphasis: "Some **bold**, some *italic*, some **bold with *italic* inside**, and _underscored_.",
  "italic inside a word": "un*believ*able",
  "bold and italic at once": "***both***",
  links: "A [link with **bold**](https://example.com/a_b) and [mail](mailto:a@b.c).",
  "an unsafe link stays text": "[click](javascript:alert(1))",
  code: "Use `rm -rf *` carefully.\n\n```\nconst a = 1;\n  indented\n```",
  lists: "- one\n- two\n  continued\n\n3. three\n4. four",
  "a quote": "> A quote\n> over lines\n>\n> - with a list",
  "a rule": "Above\n\n---\n\nBelow",
  "characters that mean something in Markdown": "2 * 3 = 6, a_b_c, _x, [not a link], \\backslash, `tick",
  "lines that look like blocks": "Text\n# not a heading\n- not a list\n1. not a number\n> not a quote\n--- not a rule\n<!-- not hidden -->",
  "HTML stays text": "<b>bold?</b> <script>alert(1)</script>",
  "a heading ending in #": "## Learning C#",
  "the built sections": BUILT,
  "an empty backstory": "",
};

describe("the editor's Markdown", () => {
  for (const [name, md] of Object.entries(SAMPLES)) {
    it(`reads back the same: ${name}`, () => {
      const written = roundTrip(md);
      expect(parseBlocks(written, true)).toEqual(parseBlocks(md, true));
      // Writing it again changes nothing.
      expect(roundTrip(written)).toBe(written);
    });
  }

  it("keeps the question marks exactly, as their own blocks", () => {
    const doc = toDoc(BUILT);
    const comments = (doc.content ?? []).filter((n) => n.type === "comment");
    expect(comments.map((n) => n.attrs?.line)).toEqual([
      "<!-- questions:0196f2a4-1111-7000-8000-000000000001 -->",
      "<!-- /questions:0196f2a4-1111-7000-8000-000000000001 -->",
    ]);
    const written = roundTrip(BUILT);
    expect(written).toContain("\n\n<!-- questions:0196f2a4-1111-7000-8000-000000000001 -->\n\n# The Pitch");
    expect(written).toContain("cruel.\n\n<!-- /questions:0196f2a4-1111-7000-8000-000000000001 -->");
  });

  it("keeps any other comment line too", () => {
    expect(roundTrip("Before\n\n<!-- a note to self -->\n\nAfter")).toBe("Before\n\n<!-- a note to self -->\n\nAfter");
  });

  it("writes formatting typed in the editor as Markdown", () => {
    const md = toMarkdown({
      type: "doc",
      content: [
        { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "Since" }] },
        {
          type: "paragraph",
          content: [
            { type: "text", text: "He was " },
            { type: "text", text: "cruel ", marks: [{ type: "bold" }] },
            { type: "text", text: "and " },
            { type: "text", text: "cold", marks: [{ type: "bold" }, { type: "italic" }] },
            { type: "hardBreak" },
            { type: "text", text: "# but this is no heading" },
          ],
        },
        { type: "bulletList", content: [{ type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "I fled" }] }] }] },
        { type: "paragraph" },
      ],
    });
    expect(md).toBe("## Since\n\nHe was **cruel** and **_cold_**\n\\# but this is no heading\n\n- I fled");
    expect(parseBlocks(md)[1]).toEqual({
      t: "p",
      c: [
        { t: "text", v: "He was " },
        { t: "strong", c: [{ t: "text", v: "cruel" }] },
        { t: "text", v: " and " },
        { t: "strong", c: [{ t: "em", c: [{ t: "text", v: "cold" }] }] },
        { t: "br" },
        { t: "text", v: "# but this is no heading" },
      ],
    });
  });

  it("splits a quote around a comment line, which can't sit inside one", () => {
    const doc = toDoc("> one\n> <!-- questions:x -->\n> two");
    expect(doc.content?.map((n) => n.type)).toEqual(["blockquote", "comment", "blockquote"]);
  });
});

describe("keeping what wasn't changed", () => {
  const normalised = roundTrip(BUILT);

  it("gives back the Markdown as it was when nothing changed", () => {
    expect(keepUnchanged(normalised, BUILT, normalised)).toBe(BUILT);
  });

  it("keeps the built sections byte for byte when only the player's own words change", () => {
    const edited = normalised.replace("My own opening", "My own new opening");
    const kept = keepUnchanged(edited, BUILT, normalised);
    expect(kept).toContain("My own new opening");
    const start = BUILT.indexOf("<!-- questions:");
    const end = BUILT.indexOf("<!-- /questions:");
    expect(kept).toContain(BUILT.slice(start, end));
    // ...and the ending, down to its last new line.
    expect(kept.endsWith("<!-- /questions:0196f2a4-1111-7000-8000-000000000001 -->\n")).toBe(true);
  });

  it("keeps the player's own words as written when only a section changes", () => {
    const original = "* a star bullet\n* another\n\n" + BUILT.slice(BUILT.indexOf("<!-- questions:"));
    const tidy = roundTrip(original);
    expect(tidy.startsWith("- a star bullet")).toBe(true);
    const kept = keepUnchanged(tidy.replace("Lord Ashe", "Lord Ashe, the bastard,"), original, tidy);
    expect(kept.startsWith("* a star bullet\n* another\n")).toBe(true);
    expect(kept).toContain("Lord Ashe, the bastard,");
  });

  it("writes it the editor's way once the marks themselves change", () => {
    const changed = normalised.replace(/<!-- \/questions:[^>]+-->/, "");
    expect(keepUnchanged(changed, BUILT, normalised)).toBe(changed);
  });
});
