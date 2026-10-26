import type { PoolModifier, TestPool } from "../../api/types";

/** A Mental, Social or Physical defence pool counts current Willpower, which the
 * tracker holds (never less than a merit like Quixotic allows). */
export function willpowerFor(pool: TestPool, current: number): number {
  return pool.adds_willpower ? Math.max(current, pool.willpower_floor ?? 0) : 0;
}

/** Whether a modifier changes a pool: all of them, every attack or defence, the
 * pools made on an attribute, or the one pool it names ("pool:dodge"). */
export function appliesTo(modifier: Pick<PoolModifier, "pools">, pool: TestPool): boolean {
  const which = modifier.pools;
  if (which === "all") return true;
  if (which === "attack") return pool.key.startsWith("attack:");
  if (which === "defense") return pool.key.startsWith("defense:");
  if (which.startsWith("pool:")) return pool.key === which.slice("pool:".length);
  return pool.parts[0]?.label === which;
}

/** The modifiers that are switched on and change this pool. */
export function changing(pool: TestPool, modifiers: PoolModifier[]): PoolModifier[] {
  return modifiers.filter((m) => m.on && appliesTo(m, pool));
}

export function total(pool: TestPool, willpower: number, modifiers: PoolModifier[] = []): number {
  return pool.total + willpowerFor(pool, willpower) + changing(pool, modifiers).reduce((sum, m) => sum + m.amount, 0);
}

const part = (label: string, value: number) => (value < 0 ? `− ${label} ${-value}` : `${label} ${value}`);

/** "Physical 6 + Dodge 3 + Slippery Customer 3", with Willpower where it counts, then each modifier that is on. */
export function breakdown(pool: TestPool, willpower: number, modifiers: PoolModifier[] = []): string {
  const parts = pool.parts.map((p) => part(p.label, p.value));
  if (pool.adds_willpower) parts.push(`Willpower ${willpowerFor(pool, willpower)}`);
  for (const m of changing(pool, modifiers)) parts.push(part(m.label, m.amount));
  return parts.join(" + ").replaceAll("+ −", "−");
}

/** What a modifier applies to, in words: "Social pools", "every attack", "Dodge". */
export function describePools(which: string, pools: TestPool[]): string {
  if (which === "all") return "every pool";
  if (which === "attack") return "every attack";
  if (which === "defense") return "every defence";
  if (which.startsWith("pool:")) return pools.find((p) => p.key === which.slice("pool:".length))?.name ?? which.slice("pool:".length);
  return `${which} pools`;
}

/** "+2 Social pools, against mortals" */
export function describe(m: Pick<PoolModifier, "amount" | "pools" | "when">, pools: TestPool[]): string {
  const sign = m.amount < 0 ? "−" : "+";
  return `${sign}${Math.abs(m.amount)} ${describePools(m.pools, pools)}${m.when ? `, ${m.when}` : ""}`;
}

/** The pools in their groups, in the order the page shows them. */
export function grouped(pools: TestPool[]): [string, TestPool[]][] {
  const groups = new Map<string, TestPool[]>();
  for (const p of pools) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups];
}

type Damage = NonNullable<TestPool["damage"]>;
/** More damage from elsewhere, such as a pool modifier that says it adds damage (#188): the seam is
 * here, and nothing passes any yet. */
export type ExtraDamage = { label: string; value: number };

export function damageTotal(damage: Damage, extra: ExtraDamage[] = []): number {
  return damage.total + extra.reduce((sum, e) => sum + e.value, 0);
}

/** "2 damage: 1 (melee) + 1 (Might)", or "2 aggravated damage: …" where a power makes it so. */
export function damageText(damage: Damage, extra: ExtraDamage[] = []): string {
  const kind = damage.type === "aggravated" ? "aggravated damage" : "damage";
  const parts = [...damage.parts, ...extra].map((p) => `${p.value} (${p.label})`).join(" + ");
  return `${damageTotal(damage, extra)} ${kind}: ${parts}`;
}

/** What an exceptional success does: the usual extra point, or more with a power like Intensity. */
export function exceptionalText(damage: Damage, extra: ExtraDamage[] = []): string {
  return `An exceptional success adds ${damage.exceptional} damage, ${damageTotal(damage, extra) + damage.exceptional} in all.`;
}

/** The short form for the printed sheet: "2 damage (4 on an exceptional success)". */
export function damageShort(damage: Damage, extra: ExtraDamage[] = []): string {
  const kind = damage.type === "aggravated" ? "aggravated damage" : "damage";
  return `${damageTotal(damage, extra)} ${kind} (${damageTotal(damage, extra) + damage.exceptional} exceptional)`;
}
