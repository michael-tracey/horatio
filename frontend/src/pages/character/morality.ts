import type { CatalogueOut, SheetOut, TraitOut } from "../../api/types";

/** The category a vampire's Morality comes from: Humanity, or a single Path (MET: VTM p. 253). */
export const MORALITY = "paths";

/** Health levels in the order a sheet lists them, worst last. */
const HEALTH = ["Healthy", "Injured", "Incapacitated"];

/** What an NPC can follow: Humanity first, as everyone starts there, then each Path by name. */
export function moralityOptions(catalogue: CatalogueOut): TraitOut[] {
  return catalogue.traits
    .filter((t) => t.category === MORALITY)
    .sort((a, b) => Number(b.name === "Humanity") - Number(a.name === "Humanity") || a.name.localeCompare(b.name));
}

/** How a Morality reads in the picker: "Humanity", or "Path of Caine". */
export function moralityLabel(name: string): string {
  return name === "Humanity" ? name : `Path of ${name}`;
}

/**
 * The Morality the sheet follows and its rating. A sheet built before an NPC
 * could hold only one shows its highest; with none, the first option, unrated.
 */
export function heldMorality(sheet: SheetOut, options: TraitOut[]): { name: string; rating: number } {
  const held = sheet.traits.filter((t) => t.category === MORALITY && (t.rating ?? 0) > 0).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0];
  return held ? { name: held.name, rating: held.rating ?? 0 } : { name: options[0]?.name ?? "", rating: 0 };
}

/**
 * The change that moves an NPC to another Morality at the rating it has; the
 * server puts the new one in the old one's place. Null when there is nothing to
 * send: it already follows that one, or follows none yet and the choice waits
 * for its first dot.
 */
export function moveMorality(held: { name: string; rating: number }, to: string): { category: string; name: string; rating: number } | null {
  if (!held.rating || to === held.name) return null;
  return { category: MORALITY, name: to, rating: held.rating };
}

/** Willpower, then the health levels in sheet order: the dot rows under Morality. */
export function willpowerAndHealth(catalogue: CatalogueOut): TraitOut[] {
  const rank = (t: TraitOut) => (HEALTH.includes(t.name) ? HEALTH.indexOf(t.name) : HEALTH.length);
  return [
    ...catalogue.traits.filter((t) => t.category === "willpower_sources"),
    ...catalogue.traits.filter((t) => t.category === "health_levels").sort((a, b) => rank(a) - rank(b)),
  ];
}
