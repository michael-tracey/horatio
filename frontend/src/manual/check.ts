import { plain } from "../markdown";
import { eachInline, imagePath, resolveLink, type Manual } from "./manual";

/**
 * What the link test (links.test.ts) checks: that every link in the manual goes to
 * a page and heading that exist, every image is there and says what it shows, each
 * page has one `# Title` and nothing deeper than `####`, and every `manualLink(...)`
 * in the app names a heading that exists. Each problem is one line naming the file
 * and the link.
 */

/** A `manualLink(...)` call in the app's code: its page and anchor, or `call` when they aren't plain strings. */
export type AppLink = { file: string; line: number; page: string; anchor: string | null; call: string };

const CALL = /\bmanualLink\(([^)]*)\)/g;
const STRING = /^\s*(["'`])([^"'`$]*)\1\s*$/;

/** The `manualLink(...)` calls in one source file. */
export function findManualLinks(file: string, source: string): AppLink[] {
  const out: AppLink[] = [];
  for (const match of source.matchAll(CALL)) {
    const line = source.slice(0, match.index).split("\n").length;
    const args = match[1]!.trim() ? match[1]!.split(",") : [];
    const [page, anchor] = args.map((a) => a.match(STRING)?.[2]);
    const literal = args.length <= 2 && args.every((a) => STRING.test(a));
    out.push({ file, line, page: literal ? (page ?? "README") : "", anchor: literal ? (anchor ?? null) : null, call: match[0] });
  }
  return out;
}

/** Where a link is in a file: the line of the first of `needles` found, for the error message. */
function lineOf(text: string, ...needles: string[]): string {
  for (const needle of needles) {
    const at = text.indexOf(needle);
    if (at !== -1) return `:${text.slice(0, at).split("\n").length}`;
  }
  return "";
}

export function checkManual(manual: Manual, appLinks: AppLink[] = []): string[] {
  const errors: string[] = [];
  const target = (page: string, anchor: string | null): string | null => {
    const found = manual.pages.get(page);
    if (!found) return `${page}.md doesn't exist`;
    if (anchor && !found.headings.some((h) => h.id === anchor)) return `${page}.md has no heading with the anchor #${anchor}`;
    return null;
  };

  for (const page of manual.pages.values()) {
    const file = `${page.name}.md`;
    const titles = page.headings.filter((h) => h.level === 1);
    const first = page.blocks[0];
    if (titles.length !== 1 || first?.t !== "heading" || first.level !== 1) {
      errors.push(`${file}: should start with exactly one "# Title" heading (it has ${titles.length})`);
    }
    for (const h of page.headings.filter((h) => h.level > 4)) errors.push(`${file}: the heading "${h.text}" is deeper than ####`);

    eachInline(page.blocks, (n) => {
      if (n.t === "link") {
        const where = `${file}${lineOf(page.text, `](${n.href})`)}`;
        const link = `[${plain(n.c)}](${n.href})`;
        const to = resolveLink(page.name, n.href);
        if (to.kind === "other") errors.push(`${where}: the link ${link} isn't to a manual page; write it as page.md#heading`);
        else if (to.kind === "page") {
          const problem = target(to.page, to.anchor);
          if (problem) errors.push(`${where}: the link ${link} is broken: ${problem}`);
        }
      } else if (n.t === "image") {
        const where = `${file}${lineOf(page.text, `![${n.alt}](${n.src})`, `](${n.src})`)}`;
        if (!n.alt) errors.push(`${where}: the image ${n.src} has no alt text; say what the screen shows`);
        if (!(imagePath(n.src) in manual.images)) errors.push(`${where}: the image ${n.src} is missing from docs/manual`);
      }
    });
  }

  for (const link of appLinks) {
    const where = `${link.file}:${link.line}`;
    if (!link.page) {
      errors.push(`${where}: ${link.call} must name its page and heading as plain strings, so this test can check them`);
      continue;
    }
    const problem = target(link.page, link.anchor);
    if (problem) errors.push(`${where}: ${link.call} is broken: ${problem}`);
  }
  return errors;
}
