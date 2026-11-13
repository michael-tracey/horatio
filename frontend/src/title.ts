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

/** The tab a row would mark open at `pathname`: as NavLink does, and the deepest if more than one. */
export function openTab<T extends { to: string; end?: boolean }>(tabs: T[], pathname: string): T | undefined {
  const here = pathname.replace(/\/$/, "");
  const opens = (t: T) => {
    const to = t.to.replace(/\/$/, "");
    return t.end ? here === to : here === to || here.startsWith(`${to}/`);
  };
  return tabs.filter(opens).sort((a, b) => b.to.length - a.to.length)[0];
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
