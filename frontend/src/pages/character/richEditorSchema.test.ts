import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";
import { toDoc, toMarkdown } from "../../backstoryMarkdown";
import { editorExtensions } from "./richEditorSchema";

const MARK = "<!-- questions:0196f2a4-2222-7000-8000-000000000002 -->";
const END = "<!-- /questions:0196f2a4-2222-7000-8000-000000000002 -->";
const BUILT = `Before.\n\n${MARK}\n\n## My sire\n\nLord Ashe.\n\n${END}\n\nAfter.`;

let editor: Editor | null = null;
afterEach(() => {
  editor?.destroy();
  editor = null;
});

function open(markdown: string, onRefused = () => {}) {
  editor = new Editor({ extensions: editorExtensions({ onRefused }), content: toDoc(markdown) });
  return editor;
}

/** Where the text `words` starts in the editor's document. */
function at(e: Editor, words: string): number {
  let found = -1;
  e.state.doc.descendants((node, pos) => {
    if (found < 0 && node.isText && node.text!.includes(words)) found = pos + node.text!.indexOf(words);
  });
  return found;
}

describe("the backstory editor", () => {
  it("holds everything a backstory's Markdown says, and writes it back the same", () => {
    const md = [
      "# Heading",
      "Text with **bold**, *italic*, `code` and a [link](https://example.com).\nA second line.",
      "- one\n- two",
      "1. first\n2. second",
      "> quoted",
      "```\ncode\n```",
      "---",
      BUILT,
    ].join("\n\n");
    const e = open(md);
    expect(toMarkdown(e.getJSON())).toBe(toMarkdown(toDoc(md)));
  });

  it("keeps the question marks through an edit between them", () => {
    const e = open(BUILT);
    e.chain().insertContentAt(at(e, "Lord Ashe") + "Lord Ashe".length, ", the bastard").run();
    const md = toMarkdown(e.getJSON());
    expect(md).toContain(`${MARK}\n\n## My sire\n\nLord Ashe, the bastard.\n\n${END}`);
  });

  it("won't delete a question mark, and says so", () => {
    let refused = 0;
    const e = open(BUILT, () => refused++);
    // From inside "Before." to inside "Lord Ashe.": across the opening mark.
    e.chain().setTextSelection({ from: at(e, "fore"), to: at(e, "Ashe") }).deleteSelection().run();
    expect(refused).toBe(1);
    expect(toMarkdown(e.getJSON())).toBe(toMarkdown(toDoc(BUILT)));
    // Selecting everything and typing over it is refused too.
    e.chain().selectAll().insertContent("Gone").run();
    expect(toMarkdown(e.getJSON())).toContain(MARK);
    // An edit that leaves the marks alone goes through.
    e.chain().setTextSelection({ from: at(e, "After"), to: at(e, "After") + 5 }).insertContent("Later").run();
    expect(toMarkdown(e.getJSON())).toContain(`${END}\n\nLater.`);
  });
});
