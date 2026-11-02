/**
 * A small Markdown reader for backstories: headings, paragraphs, emphasis, lists,
 * quotes, code and links. It reads text into a tree that React renders as elements,
 * so raw HTML is never rendered: a tag shows as the text it is. A line that is only
 * an HTML comment, such as the marks around sections built from a troupe's
 * questions, is left out. A single line break is kept as one, as people writing in
 * a box expect.
 */

export type Inline =
  | { t: "text"; v: string }
  | { t: "strong"; c: Inline[] }
  | { t: "em"; c: Inline[] }
  | { t: "code"; v: string }
  | { t: "link"; href: string; c: Inline[] }
  | { t: "br" };

export type Block =
  | { t: "heading"; level: number; c: Inline[]; text: string }
  | { t: "p"; c: Inline[] }
  | { t: "ul"; items: Inline[][] }
  | { t: "ol"; start: number; items: Inline[][] }
  | { t: "quote"; c: Block[] }
  | { t: "code"; v: string }
  | { t: "hr" }
  /** A line that is only an HTML comment, as written: kept only when asked for (the editor keeps them). */
  | { t: "comment"; v: string };

export const COMMENT = /^\s*<!--.*-->\s*$/;
const HEADING = /^ {0,3}(#{1,6})(?:\s+(.*?))?\s*#*\s*$/;
export const RULE = /^ {0,3}([-*_])(\s*\1){2,}\s*$/;
const BULLET = /^ {0,3}[-*+]\s+(.*)$/;
const NUMBER = /^ {0,3}(\d{1,9})[.)]\s+(.*)$/;
const QUOTE = /^ {0,3}>\s?(.*)$/;
const FENCE = /^ {0,3}(```|~~~)/;
export const SAFE_LINK = /^(https?:\/\/|mailto:)/i;
const ESCAPABLE = "\\`*_{}[]()#+-.!>~|<";

/** The heading lines of a backstory, as their text: the sections feedback can be on. */
export function headings(text: string): string[] {
  return parseBlocks(text)
    .filter((b): b is Extract<Block, { t: "heading" }> => b.t === "heading")
    .map((b) => b.text)
    .filter((h) => h.length > 0);
}

export function parseBlocks(text: string, keepComments = false): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  let paragraph: string[] = [];
  const endParagraph = () => {
    if (paragraph.length) blocks.push({ t: "p", c: inlineLines(paragraph) });
    paragraph = [];
  };

  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim()) {
      endParagraph();
      i++;
      continue;
    }
    if (COMMENT.test(line)) {
      endParagraph();
      if (keepComments) blocks.push({ t: "comment", v: line });
      i++;
      continue;
    }
    const fence = line.match(FENCE);
    if (fence) {
      endParagraph();
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i]!.trimStart().startsWith(fence[1]!)) code.push(lines[i++]!);
      i++;
      blocks.push({ t: "code", v: code.join("\n") });
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      endParagraph();
      const words = heading[2] ?? "";
      blocks.push({ t: "heading", level: heading[1]!.length, c: parseInline(words), text: plain(parseInline(words)) });
      i++;
      continue;
    }
    if (RULE.test(line)) {
      endParagraph();
      blocks.push({ t: "hr" });
      i++;
      continue;
    }
    const quote = line.match(QUOTE);
    if (quote) {
      endParagraph();
      const inner: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i]!)) inner.push(lines[i++]!.match(QUOTE)![1]!);
      blocks.push({ t: "quote", c: parseBlocks(inner.join("\n"), keepComments) });
      continue;
    }
    const bullet = line.match(BULLET);
    const number = line.match(NUMBER);
    if (bullet || number) {
      endParagraph();
      const pattern = bullet ? BULLET : NUMBER;
      const items: string[][] = [];
      while (i < lines.length) {
        const here = lines[i]!;
        const item = here.match(pattern);
        if (item) {
          items.push([bullet ? item[1]! : item[2]!]);
          i++;
        } else if (here.trim() && /^\s{2,}/.test(here) && items.length) {
          // An indented line goes on with the item above it.
          items[items.length - 1]!.push(here.trim());
          i++;
        } else if (!here.trim() && i + 1 < lines.length && pattern.test(lines[i + 1]!)) {
          i++;
        } else break;
      }
      const parsed = items.map((item) => inlineLines(item));
      blocks.push(number ? { t: "ol", start: Number(number[1]), items: parsed } : { t: "ul", items: parsed });
      continue;
    }
    paragraph.push(line.trim());
    i++;
  }
  endParagraph();
  return blocks;
}

function inlineLines(lines: string[]): Inline[] {
  const out: Inline[] = [];
  lines.forEach((line, n) => {
    if (n > 0) out.push({ t: "br" });
    out.push(...parseInline(line));
  });
  return out;
}

function plain(inline: Inline[]): string {
  return inline
    .map((n) => (n.t === "text" || n.t === "code" ? n.v : n.t === "br" ? " " : "c" in n ? plain(n.c) : ""))
    .join("");
}

const WORD = /[\p{L}\p{N}]/u;

/** Where the emphasis opened at `from` with `mark` closes, or -1. */
function closing(s: string, from: number, mark: string): number {
  let j = from;
  while ((j = s.indexOf(mark, j)) !== -1) {
    const before = s[j - 1];
    const after = s[j + mark.length];
    // A single mark is not part of a double one, the text before it is not
    // a space, and an underscore does not close inside a word.
    const single = mark.length > 1 || (s[j + 1] !== mark && before !== mark);
    if (single && before !== " " && before !== "\\" && !(mark[0] === "_" && after && WORD.test(after))) return j;
    j += mark.length;
  }
  return -1;
}

export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let text = "";
  const flush = () => {
    if (text) out.push({ t: "text", v: text });
    text = "";
  };
  let i = 0;
  while (i < s.length) {
    const ch = s[i]!;
    if (ch === "\\" && i + 1 < s.length && ESCAPABLE.includes(s[i + 1]!)) {
      text += s[i + 1];
      i += 2;
      continue;
    }
    if (ch === "`") {
      const end = s.indexOf("`", i + 1);
      if (end > i + 1) {
        flush();
        out.push({ t: "code", v: s.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (ch === "*" || ch === "_") {
      const double = s[i + 1] === ch;
      const mark = double ? ch + ch : ch;
      const opensWord = ch === "_" && i > 0 && WORD.test(s[i - 1]!);
      const next = s[i + mark.length];
      if (!opensWord && next && next !== " ") {
        const end = closing(s, i + mark.length, mark);
        if (end > i + mark.length) {
          flush();
          const inner = parseInline(s.slice(i + mark.length, end));
          out.push(double ? { t: "strong", c: inner } : { t: "em", c: inner });
          i = end + mark.length;
          continue;
        }
      }
    }
    if (ch === "[") {
      const close = s.indexOf("]", i + 1);
      if (close > i && s[close + 1] === "(") {
        const end = s.indexOf(")", close + 2);
        if (end > close) {
          const href = s.slice(close + 2, end).trim();
          const label = parseInline(s.slice(i + 1, close));
          if (SAFE_LINK.test(href)) {
            flush();
            out.push({ t: "link", href, c: label });
            i = end + 1;
            continue;
          }
        }
      }
    }
    text += ch;
    i++;
  }
  flush();
  return out;
}
