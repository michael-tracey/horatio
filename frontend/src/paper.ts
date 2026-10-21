import type { Preferences } from "./api/types";

export type Paper = Preferences["paper"];

/** The paper sizes people print on (#104), in inches, portrait. */
export const PAPERS: Record<Paper, { name: string; width: number; height: number; css: string }> = {
  letter: { name: "US Letter", width: 8.5, height: 11, css: "letter" },
  // 210 × 297 mm.
  a4: { name: "A4", width: 210 / 25.4, height: 297 / 25.4, css: "A4" },
};

/** The print CSS that lays a page out for this paper, with this margin. It comes
 * after index.css's US Letter default, so it wins. */
export function pageRule(paper: Paper, margin: string): string {
  return `@page { size: ${PAPERS[paper].css}; margin: ${margin}; }`;
}
