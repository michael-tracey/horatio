import type { TestPool } from "../../api/types";

/** A Mental, Social or Physical defence pool counts current Willpower, which the
 * tracker holds (never less than a merit like Quixotic allows). */
export function willpowerFor(pool: TestPool, current: number): number {
  return pool.adds_willpower ? Math.max(current, pool.willpower_floor ?? 0) : 0;
}

export function total(pool: TestPool, willpower: number): number {
  return pool.total + willpowerFor(pool, willpower);
}

/** "Physical 6 + Dodge 3 + Slippery Customer 3", with Willpower where it counts. */
export function breakdown(pool: TestPool, willpower: number): string {
  const parts = pool.parts.map((p) => (p.value < 0 ? `− ${p.label} ${-p.value}` : `${p.label} ${p.value}`));
  if (pool.adds_willpower) parts.push(`Willpower ${willpowerFor(pool, willpower)}`);
  return parts.join(" + ").replaceAll("+ −", "−");
}

/** The pools in their groups, in the order the page shows them. */
export function grouped(pools: TestPool[]): [string, TestPool[]][] {
  const groups = new Map<string, TestPool[]>();
  for (const p of pools) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups];
}
