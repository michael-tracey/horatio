import type { Charge, PlayView, PowerUse } from "../../api/types";
import { bloodOver, switchKey } from "./powers";
import type { makeTap } from "./tracker";

type TapWhat = Parameters<typeof makeTap>[0];

/** What a use reads of the Play View: its trackers, its switches and its Retainers. */
export type UseView = Pick<PlayView, "powers" | "blood" | "willpower" | "blood_name" | "health" | "beast" | "panels"> & Partial<Pick<PlayView, "retainers" | "character_id" | "charges">>;

/** The counter a use changes (#826), as it stands now. */
export function counterOf(view: Partial<Pick<PlayView, "charges">>, use: Pick<PowerUse, "charges">): Charge | undefined {
  return use.charges ? (view.charges ?? []).find((c) => c.key === use.charges!.counter) : undefined;
}

/** How many of a counter, said: "1 charge", "2 charges", "1 Grace". */
export function unitsText(counter: Pick<Charge, "unit" | "units">, n: number): string {
  return `${n} ${n === 1 ? counter.unit : counter.units}`;
}

/** The amounts a use can spend of its counter: its own, or each up to all held where the player chooses (Vengeful Strike, Vol. 2 p. 75). */
export function spendAmounts(view: Partial<Pick<PlayView, "charges">>, use: Pick<PowerUse, "charges">): number[] {
  const c = use.charges;
  const counter = counterOf(view, use);
  if (!c?.spend || !counter) return [];
  if (!c.more) return [c.spend];
  const top = Math.max(c.spend, counter.value);
  return Array.from({ length: top - c.spend + 1 }, (_, i) => c.spend + i);
}

/** Whether the counter holds enough for a use's spend (#826). */
export function canSpend(view: Partial<Pick<PlayView, "charges">>, use: Pick<PowerUse, "charges">, amount?: number): boolean {
  const c = use.charges;
  if (!c?.spend) return true;
  const counter = counterOf(view, use);
  return !!counter && counter.value >= (amount ?? c.spend);
}

/** What a use does to its counter: gained (never past its most), spent, filled or emptied (#826). */
function chargeTaps(view: UseView, use: PowerUse, amount?: number): TapWhat[] {
  const c = use.charges;
  const counter = counterOf(view, use);
  if (!c || !counter) return [];
  const change = (n: number): TapWhat[] => (n !== 0 ? [{ kind: "change", tracker: counter.key, amount: n }] : []);
  if (c.fill) return change(counter.most - counter.value);
  if (c.reset) return change(-counter.value);
  if (c.spend) return counter.value >= (amount ?? c.spend) ? change(-(amount ?? c.spend)) : [];
  return change(Math.min(c.gain, counter.most - counter.value));
}

/** The switch a use turns on, if it is off (Reaper's Due's mark). */
function switchTaps(view: UseView, use: PowerUse): TapWhat[] {
  const power = use.on ? view.powers.find((p) => p.key === use.on) : undefined;
  return power && !power.on ? [{ kind: "change", tracker: switchKey(power.key), amount: 1 }] : [];
}

/** Damage marked now, by kind. */
export function marked(view: Pick<PlayView, "health">): { normal: number; aggravated: number } {
  const marks = view.health.marks;
  const aggravated = marks.filter((m) => m === "aggravated").length;
  return { normal: marks.length - aggravated, aggravated };
}

/** What a use's cost comes to now: half the Blood held, rounded down, for Indestructible. */
export function costNow(view: Pick<PlayView, "blood" | "willpower">, use: Pick<PowerUse, "cost" | "half">): number {
  if (!use.cost) return 0;
  if (!use.half) return use.cost.amount;
  const held = use.cost.tracker === "blood" ? view.blood.value : view.willpower.value;
  return Math.floor(held / 2);
}

/** Whether there is enough to pay for it: a half cost needs at least 2 held (Vol. 2 p. 214). */
export function canPay(view: Pick<PlayView, "blood" | "willpower">, use: Pick<PowerUse, "cost" | "half">): boolean {
  if (!use.cost) return true;
  const held = use.cost.tracker === "blood" ? view.blood.value : view.willpower.value;
  return use.half ? held >= 2 : held >= use.cost.amount;
}

const heal = (damage: "normal" | "aggravated", n: number): TapWhat[] => (n > 0 ? [{ kind: "change", tracker: "health", amount: -n, damage }] : []);

/** The worst damage first: aggravated, then normal (issue #825). */
function healWorst(view: Pick<PlayView, "health">, n: number): TapWhat[] {
  const { normal, aggravated } = marked(view);
  const a = Math.min(n, aggravated);
  return [...heal("aggravated", a), ...heal("normal", Math.min(n - a, normal))];
}

/** Aggravated damage turned to normal: healed as aggravated, taken back as normal. */
function convert(n: number): TapWhat[] {
  return n > 0 ? [...heal("aggravated", n), { kind: "change", tracker: "health", amount: n, damage: "normal" }] : [];
}

/** What a use heals, converts and gains, before its cost; `asked` is what the player said, for "asked". */
function effects(view: UseView, use: PowerUse, asked?: { normal: number; aggravated: number }): TapWhat[] {
  const { normal, aggravated } = marked(view);
  const found: TapWhat[] = [];
  if (use.heal) {
    const n = use.heal.amount;
    if (use.heal.damage === "normal") found.push(...heal("normal", Math.min(n, normal)));
    if (use.heal.damage === "aggravated") found.push(...heal("aggravated", Math.min(n, aggravated)));
    if (use.heal.damage === "worst") found.push(...healWorst(view, n));
    if (use.heal.damage === "all") found.push(...heal("aggravated", aggravated), ...heal("normal", normal));
    if (use.heal.damage === "asked" && asked) {
      found.push(...heal("aggravated", Math.min(asked.aggravated, aggravated)), ...heal("normal", Math.min(asked.normal, normal)));
    }
  }
  if (use.convert_all) found.push(...convert(aggravated));
  else if (use.convert) found.push(...convert(Math.min(use.convert, aggravated)));
  if (use.mend) found.push(...(aggravated > 0 ? convert(Math.min(use.mend, aggravated)) : heal("normal", Math.min(use.mend, normal))));
  for (const g of use.gains) {
    const t = g.tracker === "blood" ? view.blood : view.willpower;
    // Mantle of Sutekh's tithes are kept even past the pool while it lasts (#854).
    if (g.tracker === "blood" && use.over && bloodOver(view)) found.push({ kind: "change", tracker: g.tracker, amount: g.amount });
    else if (t.value < t.most) found.push({ kind: "change", tracker: g.tracker, amount: Math.min(g.amount, t.most - t.value) });
  }
  return found;
}

/** The ghoul Retainers damage can be moved onto: those with health left, and animals only where the use says (#854: Beast's Vigor). */
export function ghouls(view: UseView, use?: Pick<PowerUse, "animal">): NonNullable<PlayView["retainers"]> {
  return (view.retainers ?? []).filter((r) => r.blood && r.health.value > 0 && (!use?.animal || r.animal));
}

/**
 * The taps for one press of a use (issue #825): its cost spent, naming the power,
 * then what it heals, converts, gains and takes, as ordinary taps under one Undo.
 * None when it would change nothing, so its button is off. For moving damage
 * (Beast's Vigor), `retainer` is the Retainer's key.
 */
export function effectTaps(view: UseView, use: PowerUse, power: string, opts: { asked?: { normal: number; aggravated: number }; retainer?: string; spend?: number } = {}): TapWhat[] {
  if (!canPay(view, use) || !canSpend(view, use, opts.spend)) return [];
  const made: TapWhat[] = [...effects(view, use, opts.asked)];
  if (use.retainer && opts.retainer) {
    const r = ghouls(view, use).find((g) => g.key === opts.retainer);
    const { normal, aggravated } = marked(view);
    const n = r ? Math.min(use.retainer, r.health.value, normal + aggravated) : 0;
    if (n > 0) made.push(...healWorst(view, n), { kind: "change", tracker: `${r!.key}/health`, amount: -n });
  }
  // Nothing healed, gained or moved: a Beast trait alone is a use only where it is the whole of it.
  const moved = made.length > 0;
  if (use.beast && (moved || (!use.heal && !use.convert && !use.convert_all && !use.mend && use.gains.length === 0 && !use.retainer))) {
    if (view.panels.beast) made.push({ kind: "change", tracker: "beast", amount: use.beast });
  }
  // A use that spends its counter (#826) needs something to come of it: healing, say.
  const spending = chargeTaps(view, use, opts.spend);
  if (use.charges?.spend && made.length === 0 && (use.heal || use.convert || use.convert_all || use.mend || use.gains.length || use.retainer)) return [];
  const turned = switchTaps(view, use);
  made.push(...spending, ...turned);
  // A gain at the counter's most still uses the power, for its cost (Water Mastery's third and later applications).
  const counting = !!use.charges && !use.charges.spend && !!counterOf(view, use) && costNow(view, use) > 0;
  if (made.length === 0 && !counting) return [];
  const spent = costNow(view, use);
  return [...(spent > 0 ? [{ kind: "change" as const, tracker: use.cost!.tracker, amount: -spent, note: power }] : []), ...made];
}

/** What a use's button says it costs: "1 Blood", "half your Blood (3)". */
export function costText(view: UseView, use: Pick<PowerUse, "cost" | "half">): string {
  if (!use.cost) return "";
  const what = use.cost.tracker === "blood" ? view.blood_name : "Willpower";
  return use.half ? `half your ${what} (${costNow(view, use)})` : `${use.cost.amount} ${what}`;
}

/** Whether a use is offered now: its switch, if it names one, is on. */
export function offered(view: Pick<PlayView, "powers">, use: PowerUse): boolean {
  return !use.when || view.powers.some((p) => p.key === use.when && p.on);
}
