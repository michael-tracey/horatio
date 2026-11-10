import type { PlayView, PowerSwitch } from "../../api/types";

/**
 * Forms and powers in use (issue #200), as the server works them out
 * (horatio/play.py): a tap on "power:<key>" switches one on (+1) or off (−1). Only
 * one form is on at a time (MET: VtM core, p. 114), so turning one on turns the
 * last off, unless the two combine (Mantle of Atira and Spiritwalker). With
 * Ravenous Conglomeration two can be on (Vol. 2 p. 249, issue #597): a third turns
 * off the one on longest, and a form never joins another of the same power. A form's
 * extra wound levels come after the sheet's own in each category; when it ends
 * they go, with the damage marked in them.
 */

export const SWITCH = "power:";

export const switchKey = (key: string) => `${SWITCH}${key}`;

/** What another power the character has adds to a switch (issue #601): "Quickness (p. 214): An extra round of actions…". */
export const addedNote = (added: PowerSwitch["added"][number]) => `${added.source} (${added.page}): ${added.note}`;

/**
 * A quality picked for a power each use (issue #599): "pick:Flesh of Marble/Ballistic"
 * +1 picks it while the power is on, −1 drops it. Past the power's count the oldest
 * goes, and switching the power off drops them all.
 */
export const PICK = "pick:";

export const pickKey = (key: string, quality: string) => `${PICK}${key}/${quality}`;

/** The power's key and the quality a pick names (what follows "pick:"). */
function picking(rest: string): [string, string] {
  const at = rest.lastIndexOf("/");
  return [rest.slice(0, at), rest.slice(at + 1)];
}

/**
 * "Protean: Flesh of Marble (Ballistic, Hardened)": a power with what is picked for
 * it. A view kept on the phone from before picks (#502) has none.
 */
export function withPicks(power: Pick<PowerSwitch, "name" | "picked">): string {
  const picked = power.picked ?? [];
  return picked.length ? `${power.name} (${picked.join(", ")})` : power.name;
}

/** The keys of the forms and powers on now. */
export function onKeys(view: Pick<PlayView, "powers">): string[] {
  return view.powers.filter((p) => p.on).map((p) => p.key);
}

/** The forms on now: usually none or one, two with Ravenous Conglomeration. */
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
  // Using it again means picking again (Vol. 2 p. 232).
  power.picked = [];
  power.turned_on = 0;
  view.blood.most = bloodMost(view);
  view.blood.value = Math.min(view.blood.value, view.blood.most);
  if (lost.length) said.push(`${lost.length} damage in its levels gone`);
}

/**
 * The forms on that turning `power` on ends, in the order they were switched on:
 * those it doesn't combine with past the character's limit (`forms`), oldest
 * first, and any other form of the same power.
 */
export function formsDisplaced(view: Pick<PlayView, "powers" | "forms">, power: PowerSwitch): PowerSwitch[] {
  const clash = view.powers
    .filter((p) => p.on && p.form && p.key !== power.key && !power.combines.includes(p.key) && !p.combines.includes(power.key))
    .sort((a, b) => (a.turned_on ?? 0) - (b.turned_on ?? 0));
  const others = clash.filter((p) => p.origin !== power.origin);
  const gone = new Set([...clash.filter((p) => p.origin === power.origin), ...others.slice(0, Math.max(0, others.length - ((view.forms ?? 1) - 1)))]);
  return clash.filter((p) => gone.has(p));
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
      for (const other of formsDisplaced(view, power)) {
        said.push(`out of ${other.name}`);
        switchOff(view, other, said);
      }
    }
    power.turned_on = Math.max(0, ...view.powers.map((p) => p.turned_on ?? 0)) + 1;
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

/**
 * Pick a quality for a power that is on (amount > 0), or drop it, in `view` (changed
 * in place), as the server does; null for a quality it can't pick.
 */
export function applyPick(view: Pick<PlayView, "powers">, rest: string, amount: number, said: string[] = []): [number, number] | null {
  const [key, quality] = picking(rest);
  const power = view.powers.find((p) => p.key === key);
  if (!power?.picks || !(power.options ?? []).some((o) => o.name === quality)) return null;
  const now = [...(power.picked ?? [])];
  const before = now.includes(quality) ? 1 : 0;
  if (amount > 0 && !before && power.on) {
    while (now.length && now.length >= power.picks.count) said.push(`dropped ${now.shift()} (${power.picks.count} at most)`);
    now.push(quality);
  } else if (amount < 0 && before) {
    now.splice(now.indexOf(quality), 1);
  }
  power.picked = now;
  return [before, now.includes(quality) ? 1 : 0];
}

/** The power a pick is for, by name, and the quality: ["Protean: Flesh of Marble", "Ballistic"]. */
export function pickedFor(view: Pick<PlayView, "powers">, rest: string): [string, string] {
  const [key, quality] = picking(rest);
  return [view.powers.find((p) => p.key === key)?.name ?? key, quality];
}

/** The pick as the log reads it: "Picked Ballistic for Protean: Flesh of Marble". */
export function describePick(view: Pick<PlayView, "powers">, rest: string, amount: number, said: string[] = []): string {
  const [name, quality] = pickedFor(view, rest);
  const text = amount > 0 ? `Picked ${quality} for ${name}` : `Dropped ${quality} from ${name}`;
  return said.length ? `${text}: ${said.join(", ")}` : text;
}
