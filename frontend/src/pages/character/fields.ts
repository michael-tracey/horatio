/**
 * Traits that need a detail. Skills bought once per field, such as Performance:
 * Singing (MET: VTM p. 92), and traits bought once for each of several, each
 * named, such as Retainers and Alternate Identity (pp. 98-99, 104). Which they
 * are comes from the rules (the catalogue's `needs_field` and `instance`), so the
 * sheet, the cart and the creation wizard all read the one list.
 */

import type { CatalogueOut, TraitOut } from "../../api/types";

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

/** What a trait's detail must say, in words for its box. */
export type DetailNeed = {
  kind: "field" | "name";
  label: string;
  hint: string;
  placeholder: string;
  /** Said when it is missing, without a full stop. */
  missing: string;
  /** The button for one more. */
  another: string;
};

const NAME_PLACEHOLDERS: Record<string, string> = {
  Retainers: "Such as Bocephus",
  "Alternate Identity": "Such as Dr. Ellen Marsh, coroner",
};

/** What the trait's detail must be, or null for one that needs none. */
export function detailNeed(trait: Pick<TraitOut, "name" | "needs_field" | "instance"> | undefined | null): DetailNeed | null {
  if (trait?.instance) {
    const one = trait.instance;
    return {
      kind: "name",
      label: "Name",
      hint: `Each ${one} is bought on its own, with its own dots, up to 5.`,
      placeholder: NAME_PLACEHOLDERS[trait.name] ?? "A name",
      missing: `Name each ${one}`,
      another: `Add another ${one}`,
    };
  }
  if (trait?.needs_field) {
    return { kind: "field", label: "Field", hint: "Bought once per field.", placeholder: FIELD_PLACEHOLDER, missing: fieldNeeded(trait.name), another: "Add another field" };
  }
  return null;
}

/** Traits bought once for each of several (Retainers), by category and name. */
export function isInstance(catalogue: CatalogueOut | undefined, category: string, name: string): boolean {
  return !!catalogue?.traits.some((t) => t.category === category && t.name === name && t.instance);
}
