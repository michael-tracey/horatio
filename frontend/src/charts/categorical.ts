import { SLOT_CAP, type ChartForm, type Slot } from "./palette";

/**
 * Categorical slots for things a chart tells apart (#706), in the order given:
 * the first gets slot 1, the next slot 2, and so on, never cycling. When there
 * are more than the form's cap, the last slot goes to "Other" and everything past
 * the cap less one folds into it, so no two things ever share a hue.
 *
 * Colour follows the thing, never its rank in one chart: pass the same list
 * (in the same order) to every chart that shows these things, such as a troupe's
 * clans by how many characters each has, and filtering a chart never repaints
 * what is left.
 */
export function assignSlots(keys: readonly string[], form: ChartForm = "adjacent"): Map<string, Slot> {
  const cap = SLOT_CAP[form];
  const unique = [...new Set(keys)];
  const named = unique.length > cap ? cap - 1 : unique.length;
  return new Map(unique.map((key, i) => [key, i < named ? i + 1 : "other"]));
}

/** The slot for `key`, or "other" for anything the map doesn't know. */
export function slotOf(slots: ReadonlyMap<string, Slot>, key: string): Slot {
  return slots.get(key) ?? "other";
}
