import { parseManual, plain, SAFE_LINK, type Block, type Inline } from "../markdown";
import { helpPath } from "../manualLink";
import { slugger } from "./slug";

/**
 * The user manual, from its Markdown files in docs/manual: each page read once,
 * its headings given GitHub's anchors, links between pages turned into the app's,
 * and search over the lot. The files themselves are bundled by ./content.ts; this
 * part takes them as plain text, so tests can hand it their own.
 */

export type Heading = { level: number; text: string; id: string };

export type Page = {
  /** The file's name without `.md`: `players`, or `README` for the contents. */
  name: string;
  title: string;
  /** The Markdown as written. */
  text: string;
  blocks: Block[];
  headings: Heading[];
};

export type Manual = {
  pages: Map<string, Page>;
  /** Image URLs by their path in docs/manual, such as `images/players/sheet.png`. */
  images: Record<string, string>;
};

export const CONTENTS = "README";

export function buildPage(name: string, text: string): Page {
  const blocks = parseManual(text);
  const headings: Heading[] = [];
  const id = slugger();
  const walk = (list: Block[]) => {
    for (const b of list) {
      if (b.t === "heading") {
        b.id = id(b.text);
        headings.push({ level: b.level, text: b.text, id: b.id });
      } else if (b.t === "quote") walk(b.c);
    }
  };
  walk(blocks);
  const title = headings.find((h) => h.level === 1)?.text ?? name;
  return { name, title, text, blocks, headings };
}

/** The manual from its files' text, keyed by their names (`players.md`), and its images' URLs. */
export function buildManual(files: Record<string, string>, images: Record<string, string> = {}): Manual {
  const pages = new Map<string, Page>();
  for (const [file, text] of Object.entries(files).sort(([a], [b]) => a.localeCompare(b))) {
    const name = file.replace(/\.md$/, "");
    pages.set(name, buildPage(name, text));
  }
  return { pages, images };
}

export type Target =
  /** A page of the manual, and the heading on it if the link names one. */
  | { kind: "page"; page: string; anchor: string | null; to: string }
  | { kind: "external"; href: string }
  /** Anything else, such as a link to an image or a folder: shown as its words, and failed by the link test. */
  | { kind: "other"; href: string };

/** Where a link in page `from` goes: `players.md#downtimes` is /help/players#downtimes, `#x` is on `from` itself. */
export function resolveLink(from: string, href: string): Target {
  if (SAFE_LINK.test(href)) return { kind: "external", href };
  const hash = href.indexOf("#");
  const path = (hash === -1 ? href : href.slice(0, hash)).replace(/^\.\//, "");
  let anchor: string | null = hash === -1 ? null : href.slice(hash + 1);
  try {
    if (anchor) anchor = decodeURIComponent(anchor);
  } catch {
    // Left as written.
  }
  if (anchor === "") anchor = null;
  let page: string;
  if (!path) page = from;
  else if (/^[\w-]+\.md$/.test(path)) page = path.slice(0, -3);
  else return { kind: "other", href };
  return { kind: "page", page, anchor, to: helpPath(page, anchor) };
}

/** An image's path in docs/manual as written in a page: `./images/x.png` is `images/x.png`. */
export function imagePath(src: string): string {
  return src.replace(/^\.\//, "");
}

/** A block as plain words, for search. */
export function blockText(b: Block): string {
  switch (b.t) {
    case "heading":
      return b.text;
    case "p":
      return plain(b.c);
    case "ul":
    case "ol":
      return b.items.map((item, i) => [plain(item), ...(b.children?.[i] ?? []).map(blockText)].join(" ")).join(" ");
    case "quote":
      return b.c.map(blockText).join(" ");
    case "code":
      return b.v;
    case "table":
      return [b.head, ...b.rows].map((row) => row.map(plain).join(" ")).join(" ");
    case "hr":
    case "comment":
      return "";
  }
}

export type Section = {
  page: string;
  pageTitle: string;
  /** The section's heading, or null for the words under a page's title. */
  heading: string | null;
  anchor: string | null;
  text: string;
};

/** A page cut at each `##` and deeper heading, for search: each part with the words under it. */
export function sections(page: Page): Section[] {
  const out: Section[] = [];
  let current: Section = { page: page.name, pageTitle: page.title, heading: null, anchor: null, text: "" };
  const words: string[] = [];
  const end = () => {
    current.text = words.join(" ").replace(/\s+/g, " ").trim();
    if (current.heading || current.text) out.push(current);
    words.length = 0;
  };
  for (const b of page.blocks) {
    if (b.t === "heading" && b.level === 1) continue;
    if (b.t === "heading") {
      end();
      current = { page: page.name, pageTitle: page.title, heading: b.text, anchor: b.id ?? null, text: "" };
    } else words.push(blockText(b));
  }
  end();
  return out;
}

/** The pages in the order the contents lists them, then any it doesn't, and the contents last. */
export function inOrder(manual: Manual): Page[] {
  const listed: string[] = [];
  eachInline(manual.pages.get(CONTENTS)?.blocks ?? [], (n) => {
    const target = n.t === "link" ? resolveLink(CONTENTS, n.href) : null;
    if (target?.kind === "page" && !listed.includes(target.page)) listed.push(target.page);
  });
  const rank = (name: string) => (name === CONTENTS ? Infinity : listed.includes(name) ? listed.indexOf(name) : listed.length);
  return [...manual.pages.values()].sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
}

/** Every inline node in the blocks, in order, with those inside emphasis, links and quotes. */
export function eachInline(blocks: Block[], visit: (n: Inline) => void): void {
  const inline = (list: Inline[]) => {
    for (const n of list) {
      visit(n);
      if ("c" in n) inline(n.c);
    }
  };
  for (const b of blocks) {
    if (b.t === "p" || b.t === "heading") inline(b.c);
    else if (b.t === "ul" || b.t === "ol") {
      b.items.forEach(inline);
      b.children?.forEach((inner) => inner && eachInline(inner, visit));
    }
    else if (b.t === "table") [b.head, ...b.rows].forEach((row) => row.forEach(inline));
    else if (b.t === "quote") eachInline(b.c, visit);
  }
}

export type Snippet = { text: string; match: boolean }[];
export type Hit = { section: Section; snippet: Snippet; to: string };

const SNIPPET = 180;

function escape(word: string): string {
  return word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Words of `text` around the first of `words` in it, with each of them marked. */
export function snippet(text: string, words: string[]): Snippet {
  const lower = text.toLowerCase();
  const first = Math.min(...words.map((w) => lower.indexOf(w)).filter((n) => n >= 0));
  let start = Number.isFinite(first) ? Math.max(0, first - 60) : 0;
  if (start > 0) {
    const space = text.indexOf(" ", start);
    start = space === -1 || space > first ? start : space + 1;
  }
  let end = Math.min(text.length, start + SNIPPET);
  if (end < text.length) {
    const space = text.lastIndexOf(" ", end);
    if (space > start) end = space;
  }
  const shown = (start > 0 ? "…" : "") + text.slice(start, end) + (end < text.length ? "…" : "");
  if (!words.length) return [{ text: shown, match: false }];
  const pattern = new RegExp(`(${words.map(escape).join("|")})`, "gi");
  return shown
    .split(pattern)
    .filter(Boolean)
    .map((part) => ({ text: part, match: words.includes(part.toLowerCase()) }));
}

/** Every section with all the query's words in it, best first: a word in a heading counts most. */
export function search(manual: Manual, query: string, limit = 30): Hit[] {
  const words = [...new Set(query.toLowerCase().split(/\s+/).filter(Boolean))];
  if (!words.length) return [];
  const hits: (Hit & { score: number; order: number })[] = [];
  let order = 0;
  for (const page of inOrder(manual)) {
    for (const section of sections(page)) {
      order++;
      const heading = (section.heading ?? "").toLowerCase();
      const title = section.pageTitle.toLowerCase();
      const text = section.text.toLowerCase();
      if (!words.every((w) => heading.includes(w) || text.includes(w) || title.includes(w))) continue;
      const score = words.reduce((sum, w) => sum + (heading.includes(w) ? 5 : 0) + (title.includes(w) ? 1 : 0) + Math.min(text.split(w).length - 1, 3), 0);
      hits.push({ section, snippet: snippet(section.text, words), to: helpPath(page.name, section.anchor), score, order });
    }
  }
  return hits
    .sort((a, b) => b.score - a.score || a.order - b.order)
    .slice(0, limit)
    .map(({ section, snippet, to }) => ({ section, snippet, to }));
}
