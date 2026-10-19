import type { TraitOut } from "../../api/types";

/**
 * Narrowing a long list of merits or flaws: everything, what this character can
 * take, everything for one clan or bloodline ("req:Ventrue"), or one kind
 * ("kind:General").
 */
export type TraitFilter = string;

export function filterChoices(traits: TraitOut[], canCheck: boolean): { value: TraitFilter; label: string }[] {
  const requirements = [...new Set(traits.map((t) => t.requirement).filter((r): r is string => !!r))].sort();
  const kinds = [...new Set(traits.map((t) => t.kind).filter((k): k is string => !!k))].sort();
  return [
    ...(canCheck ? [{ value: "can", label: "What this character can take" }] : []),
    { value: "all", label: "Everything" },
    ...kinds.map((k) => ({ value: `kind:${k}`, label: `${k} only` })),
    ...requirements.map((r) => ({ value: `req:${r}`, label: `For ${r}` })),
  ];
}

/**
 * The traits a filter shows. "What this character can take" leaves out `barred`:
 * what the rules refuse whatever else is chosen (another clan's merits). A trait
 * refused only because of a current choice (a clan merit of a value already
 * taken) is still shown, greyed with the reason, so unticking the other frees it.
 */
export function applyFilter(traits: TraitOut[], filter: TraitFilter, barred: Record<string, string> = {}): TraitOut[] {
  if (filter === "can") return traits.filter((t) => !(t.name in barred));
  if (filter.startsWith("kind:")) return traits.filter((t) => t.kind === filter.slice(5));
  if (filter.startsWith("req:")) {
    const wanted = filter.slice(4);
    return traits.filter((t) => t.requirement === wanted || t.requirement?.startsWith(`${wanted}:`));
  }
  return traits;
}

/**
 * One-tap filters for the character's own clan (with its bloodlines: a Telyav sees
 * every Tremere merit) and sect, where the list has any for them.
 */
export function quickPicks(traits: TraitOut[], sheet: { category: string; name: string }[]): { value: TraitFilter; label: string }[] {
  const clan = sheet.find((t) => t.category === "clan")?.name;
  const sect = sheet.find((t) => t.category === "sect")?.name;
  const picks: { value: TraitFilter; label: string }[] = [];
  const family = clan?.split(":")[0]?.trim();
  if (family && applyFilter(traits, `req:${family}`).length) picks.push({ value: `req:${family}`, label: family });
  if (sect && applyFilter(traits, `kind:${sect}`).length) picks.push({ value: `kind:${sect}`, label: sect });
  return picks;
}
