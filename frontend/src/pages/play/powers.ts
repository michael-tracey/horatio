import type { PlayView, PowerSwitch } from "../../api/types";

/**
 * Forms and powers in use (issue #200), as the server works them out
 * (horatio/play.py): a tap on "power:<key>" switches one on (+1) or off (−1). Only
 * one form is on at a time (MET: VtM core, p. 114), so turning one on turns the
 * last off, unless the two combine (Mantle of Atira and Spiritwalker). A form's
 * extra wound levels come after the sheet's own in each category; when it ends
 * they go, with the damage marked in them.
 */

export const SWITCH = "power:";

export const switchKey = (key: string) => `${SWITCH}${key}`;

/** The keys of the forms and powers on now. */
export function onKeys(view: Pick<PlayView, "powers">): string[] {
  return view.powers.filter((p) => p.on).map((p) => p.key);
}

/** The forms on now: usually none or one. */
export function formsOn(view: Pick<PlayView, "powers">): PowerSwitch[] {
  return view.powers.filter((p) => p.on && p.form);
}

/** One wound box: its category, and the form it comes from (null for the sheet's own). */
export type Box = { level: string; from: PowerSwitch | null };

/** Every wound box, in the order damage fills them. */
export function boxes(view: Pick<PlayView, "health" | "powers">): Box[] {
  const found: Box[] = [];
  const on = view.powers.filter((p) => p.on);
  for (const level of view.health.levels) {
    for (let i = 0; i < level.boxes; i++) found.push({ level: level.name, from: null });
    for (const p of on) for (const h of p.health) if (h.level === level.name) for (let i = 0; i < h.boxes; i++) found.push({ level: level.name, from: p });
  }
  return found;
}

export const healthMost = (view: Pick<PlayView, "health" | "powers">) => boxes(view).length;

/** The most Blood: half again (rounded up) with Blood of Potency on. */
export function bloodMost(view: Pick<PlayView, "blood_usual" | "powers">): number {
  return view.blood_usual + view.powers.filter((p) => p.on && p.blood_half).reduce((sum) => sum + Math.ceil(view.blood_usual / 2), 0);
}

/** Blood a turn, with what the powers on add. */
export function bloodPerTurn(view: Pick<PlayView, "blood_per_turn" | "powers">): number {
  return view.blood_per_turn + view.powers.filter((p) => p.on).reduce((sum, p) => sum + p.blood_per_turn, 0);
}

function switchOff(view: PlayView, power: PowerSwitch, said: string[]) {
  const marks = view.health.marks;
  const lost = boxes(view)
    .map((b, i) => (b.from?.key === power.key && i < marks.length ? i : -1))
    .filter((i) => i >= 0);
  for (const i of lost.reverse()) marks.splice(i, 1);
  power.on = false;
  view.blood.most = bloodMost(view);
  view.blood.value = Math.min(view.blood.value, view.blood.most);
  if (lost.length) said.push(`${lost.length} damage in its levels gone`);
}

/**
 * Switch a form or power on or off in `view` (changed in place), and say whether
 * it was on before and after, with what else changed (`said`).
 */
export function applySwitch(view: PlayView, key: string, amount: number, said: string[] = []): [number, number] | null {
  const power = view.powers.find((p) => p.key === key);
  if (!power) return null;
  const before = power.on ? 1 : 0;
  if (amount > 0 && !power.on) {
    if (power.form) {
      for (const other of view.powers.filter((p) => p.on && p.form && !power.combines.includes(p.key) && !p.combines.includes(power.key))) {
        said.push(`out of ${other.name}`);
        switchOff(view, other, said);
      }
    }
    power.on = true;
    view.blood.most = bloodMost(view);
  } else if (amount < 0 && power.on) {
    switchOff(view, power, said);
  }
  return [before, power.on ? 1 : 0];
}

/** The tap as the log reads it: "Turned into Shape of the Beast: fight form (wolf)", "Celerity on". */
export function describeSwitch(view: Pick<PlayView, "powers">, key: string, amount: number, said: string[] = []): string {
  const power = view.powers.find((p) => p.key === key);
  const name = power?.name ?? key;
  const text = power?.form ? (amount > 0 ? `Turned into ${name}` : `Out of ${name}`) : `${name} ${amount > 0 ? "on" : "off"}`;
  return said.length ? `${text}: ${said.join(", ")}` : text;
}
