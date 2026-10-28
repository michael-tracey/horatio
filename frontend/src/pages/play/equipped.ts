import type { EquipmentModifier, PlayItem, PlayView } from "../../api/types";
import type { Modifier } from "./pools";

/**
 * Equipment in use at a game (issue #306), as the server works it out
 * (horatio/play.py): a tap on "equip:<id>" equips an item (+1) or takes it off
 * (−1), and what is equipped is kept from game to game. Weapons in hand take two
 * hands at most (MET: VTM p. 516), protective gear is worn one at a time (p. 519),
 * and only one piece of miscellaneous gear's bonus counts at a time (p. 520), so
 * equipping one puts away what it would replace. While an item is equipped, each of
 * its qualities' pool effects is a modifier, as a player's own is.
 */

export const EQUIP = "equip:";

export const equipKey = (id: string) => `${EQUIP}${id}`;

const HANDS = 2;
const WEAPONS = ["melee", "ranged"];

/** The rule for each kind, as the drawer says it. */
export const LIMITS: Record<string, string> = {
  weapons: "Two hands' worth at most (p. 516).",
  protective: "One worn at a time (p. 519).",
  miscellaneous: "Only one piece's bonus counts at a time (p. 520).",
};

/**
 * What equipping `item` puts away, oldest first, and how, as the log says it:
 * weapons past two hands, the protective gear worn, the miscellaneous gear equipped.
 */
export function displaced(view: Pick<PlayView, "equipment" | "equipped">, item: PlayItem): { item: PlayItem; said: string }[] {
  const on = view.equipped.map((id) => view.equipment.find((i) => i.id === id)).filter((i): i is PlayItem => !!i && i.id !== item.id);
  if (item.kind === "protective") return on.filter((i) => i.kind === item.kind).map((i) => ({ item: i, said: `took off ${i.name} (one worn at a time)` }));
  if (item.kind === "miscellaneous") return on.filter((i) => i.kind === item.kind).map((i) => ({ item: i, said: `put away ${i.name} (one piece's bonus at a time)` }));
  const weapons = on.filter((i) => WEAPONS.includes(i.kind));
  const found: { item: PlayItem; said: string }[] = [];
  const hands = (list: PlayItem[]) => list.reduce((sum, w) => sum + (w.hands ?? 1), 0);
  while (weapons.length && hands(weapons) + (item.hands ?? 1) > HANDS) {
    const gone = weapons.shift()!;
    found.push({ item: gone, said: `put away ${gone.name} (two hands at most)` });
  }
  return found;
}

/**
 * Equip an item or take it off in `view` (changed in place), and say whether it was
 * equipped before and after, with what it put away (`said`). Null for an item the
 * character doesn't hold.
 */
export function applyEquip(view: Pick<PlayView, "equipment" | "equipped">, id: string, amount: number, said: string[] = []): [number, number] | null {
  const item = view.equipment.find((i) => i.id === id);
  if (!item) return null;
  const before = view.equipped.includes(id) ? 1 : 0;
  if (amount > 0 && !before) {
    for (const gone of displaced(view, item)) {
      view.equipped = view.equipped.filter((i) => i !== gone.item.id);
      said.push(gone.said);
    }
    view.equipped = [...view.equipped, id];
  } else if (amount < 0 && before) {
    view.equipped = view.equipped.filter((i) => i !== id);
  }
  return [before, view.equipped.includes(id) ? 1 : 0];
}

/** The tap as the log reads it: "Equipped Katana", "Equipped Chain Mail: took off Flak Vest (one worn at a time)". */
export function describeEquip(view: Pick<PlayView, "equipment">, id: string, amount: number, said: string[] = []): string {
  const name = view.equipment.find((i) => i.id === id)?.name ?? "an item";
  const text = `${amount > 0 ? "Equipped" : "Unequipped"} ${name}`;
  return said.length ? `${text}: ${said.join(", ")}` : text;
}

/** An item, with what its qualities do to the pools while it is equipped. */
type Holding = { id: string; modifiers: EquipmentModifier[] };

const bonus = (m: EquipmentModifier) => [m.quality, m.pools, m.when, m.situational].join("|");

/**
 * The modifiers the items equipped make, as the pools count them, in the order the
 * items were equipped. The same bonus from a second weapon counts once (the
 * Ambidextrous merit, p. 248).
 */
export function equipmentModifiers(items: Holding[], equipped: string[]): Modifier[] {
  const seen = new Set<string>();
  const found: Modifier[] = [];
  for (const id of equipped) {
    const item = items.find((i) => i.id === id);
    item?.modifiers.forEach((m, at) => {
      if (seen.has(bonus(m))) return;
      seen.add(bonus(m));
      found.push({ id: `${id}/${at}`, label: m.label, amount: m.amount, pools: m.pools, when: m.when, on: true, situational: m.situational });
    });
  }
  return found;
}
