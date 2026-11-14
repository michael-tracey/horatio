import type { PlayView, PowerUse } from "../../api/types";
import { bloodOver } from "./powers";
import type { makeTap } from "./tracker";

type TapWhat = Parameters<typeof makeTap>[0];

/** What a use reads of the Play View: its trackers, its switches and its Retainers. */
export type UseView = Pick<PlayView, "powers" | "blood" | "willpower" | "blood_name" | "health" | "beast" | "panels"> & Partial<Pick<PlayView, "retainers">>;

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

/** The ghoul Retainers damage can be moved onto (Beast's Vigor): those with health left. */
export function ghouls(view: UseView): NonNullable<PlayView["retainers"]> {
  return (view.retainers ?? []).filter((r) => r.blood && r.health.value > 0);
}

/**
 * The taps for one press of a use (issue #825): its cost spent, naming the power,
 * then what it heals, converts, gains and takes, as ordinary taps under one Undo.
 * None when it would change nothing, so its button is off. For moving damage
 * (Beast's Vigor), `retainer` is the Retainer's key.
 */
export function effectTaps(view: UseView, use: PowerUse, power: string, opts: { asked?: { normal: number; aggravated: number }; retainer?: string } = {}): TapWhat[] {
  if (!canPay(view, use)) return [];
  const made: TapWhat[] = [...effects(view, use, opts.asked)];
  if (use.retainer && opts.retainer) {
    const r = ghouls(view).find((g) => g.key === opts.retainer);
    const { normal, aggravated } = marked(view);
    const n = r ? Math.min(use.retainer, r.health.value, normal + aggravated) : 0;
    if (n > 0) made.push(...healWorst(view, n), { kind: "change", tracker: `${r!.key}/health`, amount: -n });
  }
  // Nothing healed, gained or moved: a Beast trait alone is a use only where it is the whole of it.
  const moved = made.length > 0;
  if (use.beast && (moved || (!use.heal && !use.convert && !use.convert_all && !use.mend && use.gains.length === 0 && !use.retainer))) {
    if (view.panels.beast) made.push({ kind: "change", tracker: "beast", amount: use.beast });
  }
  if (made.length === 0) return [];
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
