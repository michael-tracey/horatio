/**
 * Skills bought once per field, such as Performance: Singing (MET: VTM p. 92).
 * Which skills they are comes from the rules (the catalogue's `needs_field`), so
 * the sheet, the cart and the creation wizard all read the one list.
 */

import type { CatalogueOut } from "../../api/types";

/** The hint in every field box. */
export const FIELD_PLACEHOLDER = "Such as Singing";

/** What a skill held without its field says. */
export function fieldNeeded(name: string): string {
  return `${name} needs a field`;
}

/** The names of the skills that need a field. */
export function fieldSkills(catalogue: CatalogueOut | undefined): Set<string> {
  return new Set((catalogue?.traits ?? []).filter((t) => t.needs_field).map((t) => t.name));
}
