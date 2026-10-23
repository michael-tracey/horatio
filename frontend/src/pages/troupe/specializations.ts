/** The Specialisations tab's own tabs: one per kind, grouped as on a sheet. */

type Kind = { category: string; name: string; group: string };

/** The kind's part of the address: "lore", "influence-elite". */
export function kindSlug(category: string): string {
  return category.replace(/_specializations$/, "").replace(/_/g, "-");
}

/** Its tab's name: "Lore", not "Lore Specializations". */
export function kindLabel(name: string): string {
  return name.replace(/ Speciali[sz]ations$/, "");
}

/** The kinds by group, in the order they first come: Skills, then Backgrounds. */
export function kindGroups<K extends Kind>(kinds: K[]): { label: string; kinds: K[] }[] {
  const groups = new Map<string, K[]>();
  for (const kind of kinds) groups.set(kind.group, [...(groups.get(kind.group) ?? []), kind]);
  return [...groups].map(([label, inGroup]) => ({ label, kinds: inGroup }));
}
