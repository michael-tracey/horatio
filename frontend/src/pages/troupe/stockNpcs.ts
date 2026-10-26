import type { NpcKind } from "./npcKinds";

/** The disciplines and paths a kind's discipline specializations may take: its own
 * list, with "Thaumaturgy: *" standing for every Thaumaturgy path, or all of them. */
export function allowedPowers(kind: Pick<NpcKind, "any_discipline" | "specializations" | "numina">, disciplines: string[]): string[] {
  const own = kind.numina.map((n) => n.name);
  if (kind.any_discipline) return [...own, ...disciplines];
  const listed = disciplines.filter((d) => kind.specializations.some((p) => (p.endsWith(": *") ? d.startsWith(p.slice(0, -1)) : p === d)));
  return [...own, ...listed];
}

/** "Celerity up to 3": a discipline reached to its dots. */
export function expandPower(name: string, dots: number): string {
  return `${name} up to ${dots}`;
}
