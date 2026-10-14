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

export function applyFilter(traits: TraitOut[], filter: TraitFilter, unavailable: Record<string, string> = {}): TraitOut[] {
  if (filter === "can") return traits.filter((t) => !(t.name in unavailable));
  if (filter.startsWith("kind:")) return traits.filter((t) => t.kind === filter.slice(5));
  if (filter.startsWith("req:")) {
    const wanted = filter.slice(4);
    return traits.filter((t) => t.requirement === wanted || t.requirement?.startsWith(`${wanted}:`));
  }
  return traits;
}
