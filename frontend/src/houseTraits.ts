import type { CatalogueOut } from "./api/types";

/** The catalogue's house merits and flaws, by "category/name", each with its note:
 * "House merit of Night Court". */
export function houseLabels(catalogue: CatalogueOut | undefined): Map<string, string> {
  return new Map(
    (catalogue?.traits ?? []).flatMap((t) => (t.house ? [[`${t.category}/${t.name}`, t.house.label] as const] : [])),
  );
}
