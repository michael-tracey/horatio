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

/**
 * A kept power changes the normal form only (issue #822: Malleable Visage,
 * Bonecraft, core pp. 168-169): while a form is on, what it does is paused, and it
 * comes back when the form ends. True for one on that a form pauses now.
 */
export function isPaused(view: Pick<PlayView, "powers">, power: Pick<PowerSwitch, "on" | "normal_form_only">): boolean {
  return Boolean(power.on && power.normal_form_only && view.powers.some((p) => p.on && p.form));
}

/** The forms and powers on whose effects count now: on, and not paused by a form. */
export function counted(view: Pick<PlayView, "powers">): PowerSwitch[] {
  return view.powers.filter((p) => p.on && !isPaused(view, p));
}

/**
 * One of a power's own options picked (issue #821), such as Mythic Form's Tough: a
 * switch of its own ("Mythic Form/Tough"), on while it is picked and its power is.
 */
export type PickedOption = { key: string; name: string; power: PowerSwitch; health: PowerSwitch["health"]; blood_half: boolean; blood_per_turn: number; blood_extra?: number };

/** A power's own options picked, those of every power on, after the powers themselves, whose effects count now. */
export function countedOptions(view: Pick<PlayView, "powers">): PickedOption[] {
  const formOn = view.powers.some((p) => p.on && p.form);
  const found: PickedOption[] = [];
  for (const power of view.powers) {
    if (!power.on) continue;
    for (const name of power.picked ?? []) {
      const option = power.picks?.options?.find((o) => o.name === name);
      if (!option) continue;
      const pausedByForm = option.normal_form_only ?? power.normal_form_only;
      if (formOn && pausedByForm) continue;
      found.push({ key: option.key, name, power, health: option.health, blood_half: option.blood_half, blood_per_turn: option.blood_per_turn, blood_extra: option.blood_extra ?? 0 });
    }
  }
  return found;
}

/** The keys of the forms and powers on now whose effects count, and of the options picked for them (#821). */
export function onKeys(view: Pick<PlayView, "powers">): string[] {
  return [...counted(view).map((p) => p.key), ...countedOptions(view).map((o) => o.key)];
}

/** The forms on now: usually none or one, two with Ravenous Conglomeration. */
export function formsOn(view: Pick<PlayView, "powers">): PowerSwitch[] {
  return view.powers.filter((p) => p.on && p.form);
}

/**
 * One wound box: its category, and the form it comes from (null for the sheet's own),
 * with the option picked for it that adds it (Mythic Form's Tough, issue #821).
 */
export type Box = { level: string; from: PowerSwitch | null; option?: string };

/**
 * Every wound box, in the order damage fills them: in each category the sheet's own,
 * less those the powers on give up (#824: Bonecraft's Extra Limbs, back when it ends),
 * then those the forms and options on add.
 */
export function boxes(view: Pick<PlayView, "health" | "powers">): Box[] {
  const found: Box[] = [];
  const on = counted(view);
  const options = countedOptions(view);
  for (const level of view.health.levels) {
    const given = [...on, ...options].reduce((sum, p) => sum + p.health.reduce((n, h) => n + (h.level === level.name && h.boxes < 0 ? -h.boxes : 0), 0), 0);
    for (let i = 0; i < Math.max(0, level.boxes - given); i++) found.push({ level: level.name, from: null });
    for (const p of on) for (const h of p.health) if (h.level === level.name) for (let i = 0; i < h.boxes; i++) found.push({ level: level.name, from: p });
    for (const o of options) for (const h of o.health) if (h.level === level.name) for (let i = 0; i < h.boxes; i++) found.push({ level: level.name, from: o.power, option: o.name });
  }
  return found;
}

export const healthMost = (view: Pick<PlayView, "health" | "powers">) => boxes(view).length;

/** The most Blood: half again (rounded up) with Blood of Potency on, and more with a power that adds to it (#824: Second Stomach). */
export function bloodMost(view: Pick<PlayView, "blood_usual" | "powers">): number {
  const now = [...counted(view), ...countedOptions(view)];
  const halves = now.filter((p) => p.blood_half).length;
  return view.blood_usual + halves * Math.ceil(view.blood_usual / 2) + now.reduce((sum, p) => sum + (p.blood_extra ?? 0), 0);
}

/** Whether a power on lets Blood go past the pool (#854: Mantle of Sutekh's tithes, Vol. 2 p. 240). */
export function bloodOver(view: Pick<PlayView, "powers">): boolean {
  return counted(view).some((p) => p.blood_over);
}

/** Blood over the pool goes (as when a power that raised it ends), but not while a power keeps it past the pool (#854). */
function trimBlood(view: PlayView) {
  if (!bloodOver(view)) view.blood.value = Math.min(view.blood.value, view.blood.most);
}

/** The other amounts of the option `name` is one amount of (#824): "Tough: 1" and "Tough: 3" for "Tough: 2". */
export function sameOption(power: Pick<PowerSwitch, "picks">, name: string): string[] {
  const options = power.picks?.options ?? [];
  const base = options.find((o) => o.name === name)?.base;
  return base ? options.filter((o) => o.base === base && o.name !== name).map((o) => o.name) : [];
}

/** Blood a turn, with what the powers on add. */
export function bloodPerTurn(view: Pick<PlayView, "blood_per_turn" | "powers">): number {
  return view.blood_per_turn + [...counted(view), ...countedOptions(view)].reduce((sum, p) => sum + p.blood_per_turn, 0);
}

/** Take the damage marked in the wound levels these boxes are, as the levels go (Vol. 2 p. 55); how much went. */
function loseLevels(view: Pick<PlayView, "health" | "powers">, going: (b: Box) => boolean): number {
  const marks = view.health.marks;
  const lost = boxes(view)
    .map((b, i) => (going(b) && i < marks.length ? i : -1))
    .filter((i) => i >= 0);
  for (const i of lost.reverse()) marks.splice(i, 1);
  return lost.length;
}

function switchOff(view: PlayView, power: PowerSwitch, said: string[]) {
  // Its own options picked go with it (#821): their levels are its.
  const lost = loseLevels(view, (b) => b.from?.key === power.key);
  power.on = false;
  // Using it again means picking again (Vol. 2 p. 232).
  power.picked = [];
  power.turned_on = 0;
  view.blood.most = bloodMost(view);
  trimBlood(view);
  if (lost) said.push(`${lost} damage in its levels gone`);
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
  if (amount > 0 && power.on && power.kept) {
    // Used again: it replaces the one on, as a character carries one at a time (#822),
    // and its options are picked again (#821).
    said.push("replaces the one on before");
    loseLevels(view, (b) => b.from?.key === power.key && b.option !== undefined);
    power.picked = [];
    view.blood.most = bloodMost(view);
    trimBlood(view);
  } else if (amount > 0 && !power.on) {
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
export function applyPick(view: PlayView, rest: string, amount: number, said: string[] = []): [number, number] | null {
  const [key, quality] = picking(rest);
  const power = view.powers.find((p) => p.key === key);
  if (!power?.picks || !(power.options ?? []).some((o) => o.name === quality)) return null;
  const now = [...(power.picked ?? [])];
  const before = now.includes(quality) ? 1 : 0;
  const dropped: string[] = [];
  if (amount > 0 && !before && power.on) {
    // Another amount of the same option is one choice with it (#824).
    for (const other of sameOption(power, quality)) {
      if (!now.includes(other)) continue;
      now.splice(now.indexOf(other), 1);
      dropped.push(other);
      said.push(`in place of ${other}`);
    }
    while (now.length && now.length >= power.picks.count) {
      const gone = now.shift()!;
      dropped.push(gone);
      said.push(`dropped ${gone} (${power.picks.count} at most)`);
    }
    now.push(quality);
  } else if (amount < 0 && before) {
    now.splice(now.indexOf(quality), 1);
    dropped.push(quality);
  }
  // A power's own option dropped takes its levels and the damage in them (#821).
  const lost = dropped.length ? loseLevels(view, (b) => b.from?.key === power.key && b.option !== undefined && dropped.includes(b.option)) : 0;
  power.picked = now;
  view.blood.most = bloodMost(view);
  trimBlood(view);
  if (lost) said.push(`${lost} damage in its levels gone`);
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
