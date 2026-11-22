import { Mark, mergeAttributes, Node, type Extensions } from "@tiptap/core";
import Blockquote from "@tiptap/extension-blockquote";
import Bold from "@tiptap/extension-bold";
import Code from "@tiptap/extension-code";
import CodeBlock from "@tiptap/extension-code-block";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Heading from "@tiptap/extension-heading";
import HorizontalRule from "@tiptap/extension-horizontal-rule";
import Italic from "@tiptap/extension-italic";
import { BulletList, ListItem, OrderedList } from "@tiptap/extension-list";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { Gapcursor, Placeholder, TrailingNode, UndoRedo } from "@tiptap/extensions";
import type { Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { commentLabel, isQuestionsMark } from "../../backstoryMarkdown";
import { blogPictureUrl, SAFE_LINK } from "../../markdown";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    link: {
      setLink: (attributes: { href: string }) => ReturnType;
      unsetLink: () => ReturnType;
    };
  }
}

/**
 * A link, to a web or mail address only, as the Markdown reader allows. (Tiptap's own
 * link extension brings a URL finder for typing and pasting bare addresses, which a
 * backstory doesn't need.)
 */
export const Link = Mark.create({
  name: "link",
  inclusive: false,
  addAttributes() {
    return { href: { default: null } };
  },
  parseHTML() {
    return [{ tag: "a[href]", getAttrs: (el) => (SAFE_LINK.test(el.getAttribute("href") ?? "") ? { href: el.getAttribute("href") } : false) }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["a", mergeAttributes(HTMLAttributes, { rel: "noopener noreferrer nofollow" }), 0];
  },
  addCommands() {
    return {
      setLink:
        (attributes) =>
        ({ commands }) =>
          SAFE_LINK.test(attributes.href) && commands.setMark(this.name, attributes),
      unsetLink:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name, { extendEmptyMarkRange: true }),
    };
  },
});

/** The question marks in a document, in order. */
function questionMarks(doc: PmNode): string[] {
  const found: string[] = [];
  doc.forEach((node) => {
    if (node.type.name === "comment" && isQuestionsMark(String(node.attrs.line))) found.push(String(node.attrs.line));
  });
  return found;
}

/**
 * A line that is only an HTML comment, such as the marks around the sections built
 * from the troupe's questions. It shows as a divider that can't be edited, and is
 * written back exactly as it was. The question marks can't be deleted, copied or
 * moved here (answering the questions again finds its sections by them); the
 * Markdown view can still remove them.
 */
export const Comment = Node.create<{ onRefused: () => void }>({
  name: "comment",
  group: "block",
  atom: true,
  selectable: true,
  draggable: false,
  addOptions() {
    return { onRefused: () => {} };
  },
  addAttributes() {
    return { line: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "div[data-comment]", getAttrs: (el) => ({ line: el.getAttribute("data-comment") ?? "" }) }];
  },
  renderHTML({ node }) {
    const line = String(node.attrs.line);
    return [
      "div",
      { "data-comment": line, contenteditable: "false" },
      commentLabel(line),
    ];
  },
  addProseMirrorPlugins() {
    const refused = () => this.options.onRefused();
    return [
      new Plugin({
        key: new PluginKey("keepQuestionMarks"),
        filterTransaction: (tr, state) => {
          if (!tr.docChanged) return true;
          const before = questionMarks(state.doc);
          const after = questionMarks(tr.doc);
          if (before.length === after.length && before.every((m, i) => m === after[i])) return true;
          refused();
          return false;
        },
      }),
    ];
  },
});

const PICTURE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * A picture in a blog article's words (#1163), uploaded for the article: shown as it
 * will be, a block of its own, chosen as a whole and deleted with Backspace. Only
 * the blog's own pictures, by their id, can be one; a picture pasted from anywhere
 * else is left out.
 */
export const BlogPicture = Node.create({
  name: "blogPicture",
  group: "block",
  atom: true,
  selectable: true,
  draggable: false,
  addAttributes() {
    return { id: { default: "" }, alt: { default: "" }, caption: { default: "" } };
  },
  parseHTML() {
    return [
      {
        tag: "figure[data-blog-picture]",
        getAttrs: (el) => {
          const id = el.getAttribute("data-blog-picture") ?? "";
          if (!PICTURE_ID.test(id)) return false;
          return { id, alt: el.querySelector("img")?.getAttribute("alt") ?? "", caption: el.querySelector("figcaption")?.textContent ?? "" };
        },
      },
    ];
  },
  renderHTML({ node }) {
    const id = String(node.attrs.id);
    const caption = String(node.attrs.caption);
    return [
      "figure",
      { "data-blog-picture": id, contenteditable: "false" },
      ["img", { src: `${blogPictureUrl(id)}/600.webp`, alt: String(node.attrs.alt) }],
      ...(caption ? [["figcaption", {}, caption]] : []),
    ];
  },
});

/**
 * What the editor can hold: exactly what a backstory's Markdown says (see
 * markdown.ts), so nothing is lost on the way back. A list item holds one
 * paragraph, as the reader has no nested lists. A blog article's words hold its
 * `pictures` too.
 */
export function editorExtensions({ placeholder = "", onRefused = () => {}, pictures = false }: { placeholder?: string; onRefused?: () => void; pictures?: boolean } = {}): Extensions {
  return [
    Document,
    Paragraph,
    Text,
    Heading.configure({ levels: [1, 2, 3, 4, 5, 6] }),
    Bold,
    Italic,
    Code,
    Link,
    BulletList,
    OrderedList,
    ListItem.extend({ content: "paragraph" }),
    Blockquote.extend({ content: "(paragraph | heading | bulletList | orderedList | codeBlock | horizontalRule | blockquote)+" }),
    CodeBlock,
    HorizontalRule,
    HardBreak,
    UndoRedo,
    // Room to write after a comment ending the backstory, and the cursor between two.
    TrailingNode,
    Gapcursor,
    Placeholder.configure({ placeholder }),
    Comment.configure({ onRefused }),
    ...(pictures ? [BlogPicture] : []),
  ];
}
