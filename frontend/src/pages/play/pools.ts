import type { PoolModifier, SwitchedPart, TestPool } from "../../api/types";

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

/** What the forms and powers on (issue #200) change in this pool: parts they add, and attribute changes. */
function switchedOn(pool: TestPool, on: readonly string[]): { adds: SwitchedPart[]; attributes: SwitchedPart[] } {
  const now = pool.switched.filter((s) => on.includes(s.switch));
  return { adds: now.filter((s) => !s.attribute && s.value), attributes: now.filter((s) => s.attribute) };
}

/**
 * The pool's own parts with the forms and powers on: an attribute a form changes
 * is shown as it counts now ("Physical (flight form) 3"), and what they add follows.
 */
export function partsOn(pool: TestPool, on: readonly string[] = []): { label: string; value: number }[] {
  const { adds, attributes } = switchedOn(pool, on);
  const parts = pool.parts.map((p) => {
    const changes = attributes.filter((a) => a.attribute === p.label);
    if (!changes.length) return p;
    let value = p.value + changes.reduce((sum, a) => sum + a.value, 0);
    for (const a of changes) if (a.most !== null && a.most !== undefined) value = Math.min(value, a.most);
    return { label: changes.map((a) => a.label).join(", "), value: Math.max(0, value) };
  });
  return [...parts, ...adds.map((a) => ({ label: a.label, value: a.value }))];
}

export function total(pool: TestPool, willpower: number, modifiers: PoolModifier[] = [], on: readonly string[] = []): number {
  const own = partsOn(pool, on).reduce((sum, p) => sum + p.value, 0) - pool.parts.reduce((sum, p) => sum + p.value, 0);
  return pool.total + own + willpowerFor(pool, willpower) + changing(pool, modifiers).reduce((sum, m) => sum + m.amount, 0);
}

const part = (label: string, value: number) => (value < 0 ? `− ${label} ${-value}` : `${label} ${value}`);

/**
 * "Physical 6 + Dodge 3 + Slippery Customer 3", with Willpower where it counts, then
 * what the forms and powers on add ("+ Shape of the Beast 2"), then each modifier that is on.
 */
export function breakdown(pool: TestPool, willpower: number, modifiers: PoolModifier[] = [], on: readonly string[] = []): string {
  const own = partsOn(pool, on);
  const parts = own.slice(0, pool.parts.length).map((p) => part(p.label, p.value));
  if (pool.adds_willpower) parts.push(`Willpower ${willpowerFor(pool, willpower)}`);
  for (const p of own.slice(pool.parts.length)) parts.push(part(p.label, p.value));
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
/**
 * More damage from elsewhere: what the forms and powers on do to an attack (issue
 * #200), and the seam for a pool modifier that adds damage (#188), which nothing
 * passes yet. `exceptional` adds to what an exceptional success adds; `type` can
 * make the damage aggravated (Feral Claws).
 */
export type ExtraDamage = { label: string; value: number; exceptional?: number; type?: "normal" | "aggravated" };

/** What the forms and powers on do to this attack's damage. */
export function switchedDamage(damage: Damage, on: readonly string[]): ExtraDamage[] {
  return damage.switched.filter((s) => on.includes(s.switch)).map((s) => ({ label: s.label, value: s.amount, exceptional: s.exceptional, type: s.type }));
}

export function damageTotal(damage: Damage, extra: ExtraDamage[] = []): number {
  return damage.total + extra.reduce((sum, e) => sum + e.value, 0);
}

const exceptionalOf = (damage: Damage, extra: ExtraDamage[]) => damage.exceptional + extra.reduce((sum, e) => sum + (e.exceptional ?? 0), 0);

const kindOf = (damage: Damage, extra: ExtraDamage[]) =>
  damage.type === "aggravated" || extra.some((e) => e.type === "aggravated") ? "aggravated damage" : "damage";

/** "2 damage: 1 (melee) + 1 (Might)", or "2 aggravated damage: …" where a power makes it so. */
export function damageText(damage: Damage, extra: ExtraDamage[] = []): string {
  const parts = [...damage.parts, ...extra.filter((e) => e.value)].map((p) => `${p.value} (${p.label})`).join(" + ");
  const by = extra.filter((e) => e.type === "aggravated").map((e) => e.label);
  return `${damageTotal(damage, extra)} ${kindOf(damage, extra)}: ${parts}${by.length && damage.type !== "aggravated" ? `, aggravated by ${by.join(" and ")}` : ""}`;
}

/** What an exceptional success does: the usual extra point, or more with a power like Intensity. */
export function exceptionalText(damage: Damage, extra: ExtraDamage[] = []): string {
  const more = exceptionalOf(damage, extra);
  return `An exceptional success adds ${more} damage, ${damageTotal(damage, extra) + more} in all.`;
}

/** The short form for the printed sheet: "2 damage (4 on an exceptional success)". */
export function damageShort(damage: Damage, extra: ExtraDamage[] = []): string {
  return `${damageTotal(damage, extra)} ${kindOf(damage, extra)} (${damageTotal(damage, extra) + exceptionalOf(damage, extra)} exceptional)`;
}

/** The groups with the fight first (Combat, whose attacks and Dodge a scene needs, then Defence), then the rest as they came. */
export function fightFirst(groups: [string, TestPool[]][]): [string, TestPool[]][] {
  const rank = (group: string) => ["Combat", "Defence"].indexOf(group) + 1 || 3;
  return [...groups].sort((a, b) => rank(a[0]) - rank(b[0]));
}

const isAttack = (pool: TestPool) => pool.key.startsWith("attack:");

/** The attacks with the highest totals now, best first; equal totals keep the book's order. */
export function topAttacks(pools: TestPool[], willpower: number, modifiers: PoolModifier[] = [], on: readonly string[] = [], count = 3): TestPool[] {
  const now = (p: TestPool) => total(p, willpower, modifiers, on);
  return pools
    .filter(isAttack)
    .sort((a, b) => now(b) - now(a))
    .slice(0, count);
}

/** "Unarmed 9 (2 dmg)": an attack's total and its damage with the forms and powers on. */
export function attackGlance(pool: TestPool, willpower: number, modifiers: PoolModifier[] = [], on: readonly string[] = []): string {
  const dmg = pool.damage ? ` (${damageTotal(pool.damage, switchedDamage(pool.damage, on))} dmg)` : "";
  return `${pool.name.replace(/ attack$/, "")} ${total(pool, willpower, modifiers, on)}${dmg}`;
}

/** "Dodge 8 · vs Social 7 · vs Mental 7": Dodge, then each defence against a power. */
export function defenceGlance(pools: TestPool[], willpower: number, modifiers: PoolModifier[] = [], on: readonly string[] = []): string[] {
  const now = (p: TestPool) => total(p, willpower, modifiers, on);
  const dodge = pools.filter((p) => p.key === "dodge").map((p) => `Dodge ${now(p)}`);
  const resisting = pools.filter((p) => p.key.startsWith("defense:")).map((p) => `vs ${p.key.slice("defense:".length)} ${now(p)}`);
  return [...dodge, ...resisting];
}
