/** Specialisations on the printed sheet: in brackets after their skill or background. */

type TraitLike = {
  category: string;
  name: string;
  detail: string;
  pending_from: number | null;
  specializes?: { [key: string]: string } | null;
};

/** About how many characters a printed column holds, and how many its dots take. */
const COLUMN = 30;
const DOTS = 6;

const key = (category: string, name: string) => `${category}/${name}`;

/** A specialisation's name: the catalogue's, or the text of a "Custom" one. */
export function specialtyName(t: TraitLike): string {
  if (t.name === "Custom") return t.detail;
  return t.detail ? `${t.name}: ${t.detail}` : t.name;
}

/**
 * Each held skill or background's specialisations, by name, keyed by the parent
 * it `specializes`; one awaiting approval says so. Those whose parent is not on
 * the sheet are left over, to print on their own.
 */
export function specialtiesByParent<T extends TraitLike>(traits: T[]) {
  const held = new Set(traits.filter((t) => !t.specializes).map((t) => key(t.category, t.name)));
  const byParent = new Map<string, string[]>();
  const orphans: T[] = [];
  for (const t of traits) {
    if (!t.specializes) continue;
    const parent = key(t.specializes.category ?? "", t.specializes.name ?? "");
    if (!held.has(parent)) {
      orphans.push(t);
      continue;
    }
    const name = specialtyName(t) + (t.pending_from !== null ? " awaiting approval" : "");
    byParent.set(parent, [...(byParent.get(parent) ?? []), name]);
  }
  return { of: (t: { category: string; name: string }) => byParent.get(key(t.category, t.name)) ?? [], orphans };
}

/** "(French, Latin)", or "" for none. */
export function bracketed(names: string[]): string {
  return names.length ? `(${names.join(", ")})` : "";
}

/** Whether a trait's name and its bracketed specialisations fit on its line beside the dots. */
export function fitsInline(label: string, brackets: string): boolean {
  return `${label} ${brackets}`.length <= COLUMN - DOTS;
}
