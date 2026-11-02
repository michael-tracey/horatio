/**
 * The backstory editor's bridge to Markdown (issue #426). The backstory is kept as
 * Markdown, and read everywhere by our own small reader (markdown.ts), so the editor
 * reads it with that same reader and writes it back in the same dialect: what the
 * player sees as they write is what the sheet, the print sheet and the storytellers
 * see. A single line break is a plain new line, as the reader expects; HTML stays
 * text; and a line that is only an HTML comment, such as the marks around the
 * sections built from the troupe's questions, is kept exactly as written.
 */
import type { JSONContent } from "@tiptap/core";
import { COMMENT, parseBlocks, RULE, SAFE_LINK, type Block, type Inline } from "./markdown";

type Mark = { type: string; attrs?: Record<string, unknown> };

/** A mark around the sections built from one of the troupe's question sets. */
const QUESTIONS = /^\s*<!--\s*(\/?)questions:\S+\s*-->\s*$/;

/** What a comment line shows as in the editor, where it can't be edited. */
export function commentLabel(line: string): string {
  const questions = line.match(QUESTIONS);
  if (questions) return questions[1] ? "End of the troupe's questions" : "From the troupe's questions";
  return `Hidden note: ${line.trim().replace(/^<!--\s*|\s*-->$/g, "")}`;
}

export const isQuestionsMark = (line: string) => QUESTIONS.test(line);

// --- Markdown to the editor's document -------------------------------------------------------

export function toDoc(markdown: string): JSONContent {
  // A comment can't hold the cursor, so there is always a paragraph to write in
  // before and after one; left empty, it writes back as nothing.
  const content: JSONContent[] = [];
  for (const node of blocks(parseBlocks(markdown, true))) {
    if (node.type === "comment" && (!content.length || content[content.length - 1]!.type === "comment")) content.push({ type: "paragraph" });
    content.push(node);
  }
  if (!content.length || content[content.length - 1]!.type === "comment") content.push({ type: "paragraph" });
  return { type: "doc", content };
}

function blocks(list: Block[]): JSONContent[] {
  return list.flatMap(block);
}

function block(b: Block): JSONContent[] {
  switch (b.t) {
    case "heading":
      return [{ type: "heading", attrs: { level: b.level }, content: inline(b.c) }];
    case "p":
      return [{ type: "paragraph", content: inline(b.c) }];
    case "ul":
      return [{ type: "bulletList", content: b.items.map(item) }];
    case "ol":
      return [{ type: "orderedList", attrs: { start: b.start }, content: b.items.map(item) }];
    case "quote":
      return quote(blocks(b.c));
    case "code":
      return [{ type: "codeBlock", content: b.v ? [{ type: "text", text: b.v }] : [] }];
    case "hr":
      return [{ type: "horizontalRule" }];
    case "comment":
      return [{ type: "comment", attrs: { line: b.v } }];
  }
}

function item(c: Inline[]): JSONContent {
  return { type: "listItem", content: [{ type: "paragraph", content: inline(c) }] };
}

/** A quote, split around any comment line in it: a comment stands on its own. */
function quote(inner: JSONContent[]): JSONContent[] {
  const out: JSONContent[] = [];
  let run: JSONContent[] = [];
  const end = () => {
    if (run.length) out.push({ type: "blockquote", content: run });
    run = [];
  };
  for (const node of inner) {
    if (node.type === "comment") {
      end();
      out.push(node);
    } else run.push(node);
  }
  end();
  return out.length ? out : [{ type: "blockquote", content: [{ type: "paragraph" }] }];
}

function inline(nodes: Inline[], marks: Mark[] = []): JSONContent[] {
  const add = (mark: Mark) => (marks.some((m) => m.type === mark.type) ? marks : [...marks, mark]);
  return nodes.flatMap((n): JSONContent[] => {
    switch (n.t) {
      case "text":
        return n.v ? [text(n.v, marks)] : [];
      case "br":
        return [{ type: "hardBreak" }];
      case "strong":
        return inline(n.c, add({ type: "bold" }));
      case "em":
        return inline(n.c, add({ type: "italic" }));
      case "code":
        // Code takes no other mark in the editor.
        return n.v ? [text(n.v, [{ type: "code" }])] : [];
      case "link":
        return inline(n.c, add({ type: "link", attrs: { href: n.href } }));
    }
  });
}

function text(value: string, marks: Mark[]): JSONContent {
  return marks.length ? { type: "text", text: value, marks } : { type: "text", text: value };
}

// --- the editor's document to Markdown -------------------------------------------------------

export function toMarkdown(doc: JSONContent): string {
  return blocksOut(doc.content ?? []).join("\n\n");
}

function blocksOut(nodes: JSONContent[]): string[] {
  return nodes.map(blockOut).filter((s): s is string => s !== null);
}

function blockOut(node: JSONContent): string | null {
  const content = node.content ?? [];
  switch (node.type) {
    case "paragraph": {
      const lines = linesOut(content).map(guard);
      return lines.some((l) => l) ? lines.join("\n") : null;
    }
    case "heading": {
      const words = linesOut(content).join(" ").trim();
      if (!words) return null;
      const level = Math.min(Math.max(Number(node.attrs?.level) || 1, 1), 6);
      // A heading's closing #s are dropped when read, so one ending in # gets a closing one.
      return `${"#".repeat(level)} ${words}${words.endsWith("#") ? " #" : ""}`;
    }
    case "bulletList":
      return content.map((li) => `- ${itemOut(li)}`).join("\n") || null;
    case "orderedList": {
      const start = Number(node.attrs?.start ?? 1) || 1;
      return content.map((li, i) => `${start + i}. ${itemOut(li)}`).join("\n") || null;
    }
    case "blockquote": {
      const inner = blocksOut(content).join("\n\n");
      return inner
        .split("\n")
        .map((line) => (line ? `> ${line}` : ">"))
        .join("\n");
    }
    case "codeBlock": {
      const code = content.map((n) => n.text ?? "").join("");
      const fence = /^\s*```/m.test(code) ? "~~~" : "```";
      return code ? `${fence}\n${code}\n${fence}` : `${fence}\n${fence}`;
    }
    case "horizontalRule":
      return "---";
    case "comment":
      return String(node.attrs?.line ?? "") || null;
    default:
      return content.length ? blocksOut(content).join("\n\n") || null : null;
  }
}

/** A list item: its first line after the bullet, and any further lines indented under it. */
function itemOut(li: JSONContent): string {
  const lines = (li.content ?? []).flatMap((p) => (p.type === "paragraph" ? linesOut(p.content ?? []) : blocksOut([p]))).filter((l) => l);
  // Indented four spaces, a further line can't be read as the next item.
  return lines.map((l, i) => (i ? `    ${l}` : l)).join("\n");
}

/**
 * Stop a paragraph's line being read as something else: a heading, a list item,
 * a quote, a rule, a code fence or a comment.
 */
function guard(line: string): string {
  if (/^#{1,6}(\s|$)/.test(line) || /^[-+*]\s/.test(line) || /^>/.test(line) || /^(```|~~~)/.test(line) || RULE.test(line) || COMMENT.test(line)) {
    return `\\${line}`;
  }
  const number = line.match(/^(\d{1,9})([.)])(\s.*)$/);
  return number ? `${number[1]}\\${number[2]}${number[3]}` : line;
}

type Run = { text: string; marks: Mark[] };
type Token = { open: Mark; id: number } | { close: Mark; id: number } | { text: string };

const EMPHASIS = new Set(["bold", "italic"]);
const ORDER = ["link", "bold", "italic", "code"];
const WORD = /[\p{L}\p{N}]/u;
const sameMark = (a: Mark, b: Mark) => a.type === b.type && (a.type !== "link" || a.attrs?.href === b.attrs?.href);

/** A paragraph's inline content as lines of Markdown: a hard break starts a new line. */
function linesOut(nodes: JSONContent[]): string[] {
  const lines: JSONContent[][] = [[]];
  for (const node of nodes) {
    if (node.type === "hardBreak") lines.push([]);
    else lines[lines.length - 1]!.push(node);
  }
  return lines.map(lineOut);
}

function lineOut(nodes: JSONContent[]): string {
  const runs: Run[] = nodes
    .filter((n) => n.type === "text" && n.text)
    .map((n) => ({ text: n.text!.replace(/\n/g, " "), marks: marksOf(n.marks ?? []) }));
  return render(tokens(shiftSpaces(runs))).trim();
}

/** The marks Markdown can say, in order, without a link that isn't safe to follow. */
function marksOf(marks: Mark[]): Mark[] {
  const known = marks.filter((m) => ORDER.includes(m.type) && (m.type !== "link" || SAFE_LINK.test(String(m.attrs?.href ?? ""))));
  const code = known.find((m) => m.type === "code");
  return (code ? [code] : known).sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type));
}

/**
 * Bold and italic can't start or end with a space in Markdown ("** bold**" isn't
 * bold), so the spaces at either end of an emphasised run move outside it.
 */
function shiftSpaces(runs: Run[]): Run[] {
  const out: Run[] = [];
  runs.forEach((run, i) => {
    if (!run.marks.some((m) => EMPHASIS.has(m.type))) return out.push(run);
    const [, lead = "", core = "", trail = ""] = run.text.match(/^(\s*)(.*?)(\s*)$/s) ?? [];
    const keep = (neighbour: Run | undefined) => run.marks.filter((m) => !EMPHASIS.has(m.type) || neighbour?.marks.some((n) => sameMark(m, n)));
    if (!core) return out.push({ text: run.text, marks: keep(runs[i - 1]).filter((m) => keep(runs[i + 1]).includes(m)) });
    if (lead) out.push({ text: lead, marks: keep(runs[i - 1]) });
    out.push({ text: core, marks: run.marks });
    if (trail) out.push({ text: trail, marks: keep(runs[i + 1]) });
  });
  return out;
}

/**
 * The runs as opening marks, text and closing marks. A mark already open stays open
 * while the next run has it too, so "**bold *and italic* bold**" nests as written.
 */
function tokens(runs: Run[]): Token[] {
  const out: Token[] = [];
  let open: { mark: Mark; id: number }[] = [];
  let next = 0;
  for (const run of runs) {
    let keep = 0;
    while (keep < open.length && run.marks.some((m) => sameMark(m, open[keep]!.mark))) keep++;
    for (let j = open.length - 1; j >= keep; j--) out.push({ close: open[j]!.mark, id: open[j]!.id });
    open = open.slice(0, keep);
    for (const mark of run.marks) {
      if (open.some((o) => sameMark(o.mark, mark))) continue;
      const id = next++;
      out.push({ open: mark, id });
      open.push({ mark, id });
    }
    out.push({ text: run.marks.some((m) => m.type === "code") ? run.text : escape(run.text) });
  }
  for (let j = open.length - 1; j >= 0; j--) out.push({ close: open[j]!.mark, id: open[j]!.id });
  return out;
}

function render(list: Token[]): string {
  // Italic is _x_ where it can be, so it never runs into bold's **; inside a word,
  // where an underscore doesn't count, it is *x*.
  const delimiter = new Map<number, string>();
  const textNear = (from: number, step: 1 | -1) => {
    for (let i = from; i >= 0 && i < list.length; i += step) {
      const t = list[i]!;
      if ("text" in t && t.text) return step === 1 ? t.text[0] : t.text[t.text.length - 1];
      if (!("text" in t)) return undefined; // another mark's delimiter, never a word
    }
    return undefined;
  };
  list.forEach((t, i) => {
    if (!("open" in t) || t.open.type !== "italic") return;
    const end = list.findIndex((u, j) => j > i && "close" in u && u.id === t.id);
    const before = textNear(i - 1, -1);
    const after = textNear(end + 1, 1);
    delimiter.set(t.id, (before && WORD.test(before)) || (after && WORD.test(after)) ? "*" : "_");
  });
  return list
    .map((t) => {
      if ("text" in t) return t.text;
      const mark = "open" in t ? t.open : t.close;
      switch (mark.type) {
        case "bold":
          return "**";
        case "italic":
          return delimiter.get(t.id) ?? "*";
        case "code":
          return "`";
        case "link":
          return "open" in t ? "[" : `](${String(mark.attrs?.href ?? "")})`;
        default:
          return "";
      }
    })
    .join("");
}

/** Text as Markdown that reads back as the same text. */
function escape(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    // An underscore inside a word can neither open nor close emphasis.
    if (ch === "_" && WORD.test(text[i - 1] ?? "") && WORD.test(text[i + 1] ?? "")) out += ch;
    else out += "\\`*_[".includes(ch) ? `\\${ch}` : ch;
  }
  return out;
}

// --- keeping what wasn't changed exactly as it was -------------------------------------------

/** Markdown split at its comment lines: the lines between them, and the comments. */
function pieces(markdown: string): { parts: string[][]; comments: string[] } {
  const parts: string[][] = [[]];
  const comments: string[] = [];
  for (const line of markdown.split("\n")) {
    if (COMMENT.test(line)) {
      comments.push(line);
      parts.push([]);
    } else parts[parts.length - 1]!.push(line);
  }
  return { parts, comments };
}

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/**
 * The editor writes Markdown in its own tidy way, which may differ from how it was
 * written (a `*` bullet becomes `-`, spacing changes). So that opening and editing
 * one part never rewrites the rest, each part between comment lines that the player
 * hasn't changed is put back exactly as it was. That keeps the sections built from
 * the troupe's questions byte for byte, so they aren't taken for edited ones.
 *
 * `original` is the Markdown the editor opened, `normalised` the editor's own
 * writing of it before any change, and `current` its writing now.
 */
export function keepUnchanged(current: string, original: string, normalised: string): string {
  if (current === normalised) return original;
  const now = pieces(current);
  const was = pieces(original);
  const tidy = pieces(normalised);
  if (!same(now.comments, tidy.comments) || !same(tidy.comments, was.comments)) return current;
  const lines: string[] = [];
  now.parts.forEach((part, i) => {
    if (i > 0) lines.push(now.comments[i - 1]!);
    lines.push(...(same(part, tidy.parts[i]!) ? was.parts[i]! : part));
  });
  return lines.join("\n");
}
