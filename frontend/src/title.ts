import { isValidElement, useEffect } from "react";
import type { ReactNode, RefObject } from "react";

/**
 * The browser tab's title (#775), most specific first: "Approvals · ‹troupe› ·
 * Horatio". The page's heading (`PageTitle`) and its open tabs (`Tabs`,
 * `GroupedTabs`, `SubTabs`, `PageTabs`) each give a part, so a page gets its
 * title without code of its own. A page with neither, such as the Play View or
 * a printed sheet, names itself with `useTitle`. A part is only ever what the
 * page already shows, so a signed-out page names nothing it couldn't show.
 */
export const SITE = "Horatio";

/** The title from its parts, most specific first: each part once, then the site. */
export function titleOf(parts: string[]): string {
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const part of parts) {
    const text = part.replace(/\s+/g, " ").trim();
    if (text && !seen.has(text)) {
      seen.add(text);
      kept.push(text);
    }
  }
  return [...kept, SITE].join(" · ");
}

/**
 * The words of a heading, without what its components draw: a name and not the
 * pronouns or picture beside it. Only text written into the heading counts.
 */
export function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  // An element's children, not what a component draws for itself (an Avatar, Pronouns).
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

/** A tab of a row: where it goes, and `also` an address under which it is open too,
 * such as a narrator's My work, open inside a cycle's own My work (#789). */
type Openable = { to: string; end?: boolean; also?: string };

/** Whether a tab is open at `pathname`: as NavLink marks it, or under its `also`. */
export function tabOpens(t: Openable, pathname: string): boolean {
  const here = pathname.replace(/\/$/, "");
  const under = (to: string) => {
    const at = to.replace(/\/$/, "");
    return here === at || here.startsWith(`${at}/`);
  };
  if (t.end) return here === t.to.replace(/\/$/, "");
  return under(t.to) || (t.also !== undefined && under(t.also));
}

/** The tab a row would mark open at `pathname`: as NavLink does, and the deepest if more than one. */
export function openTab<T extends Openable>(tabs: T[], pathname: string): T | undefined {
  return tabs.filter((t) => tabOpens(t, pathname)).sort((a, b) => b.to.length - a.to.length)[0];
}

type Part = { text: string; node: Element | null };
const parts = new Map<number, Part>();
let nextId = 0;

/** Later on the page is more specific: a tab under the heading, a page inside a tab. */
function apply() {
  const shown = [...parts.entries()].sort(([a, p], [b, q]) => {
    // A part with no place on the page (`useTitle` alone) names the whole page: least specific.
    if (!p.node || !q.node) return p.node ? 1 : q.node ? -1 : a - b;
    if (p.node === q.node) return a - b;
    return p.node.compareDocumentPosition(q.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });
  document.title = titleOf(shown.map(([, p]) => p.text).reverse());
}

/**
 * Adds `text` to the tab's title while the component is shown, placed by where
 * `at` is on the page; without `at`, it names the whole page. Nothing for an
 * empty text.
 */
export function useTitle(text: string | null | undefined, at?: RefObject<Element | null>) {
  useEffect(() => {
    if (!text) return;
    const id = nextId++;
    parts.set(id, { text, node: at?.current ?? null });
    apply();
    return () => {
      parts.delete(id);
      apply();
    };
  }, [text, at]);
}
