import { interpolateLab } from "d3-interpolate";

/**
 * The colours charts draw with (#706), by the job each does: identity
 * (categorical), how much (sequential), which side of nothing (diverging). The
 * values are the dataviz method's validated reference palette, checked against
 * Horatio's own surfaces with its validator: every categorical slot passes on
 * Dark's night (#141016) and dusk (#1e1922) and Ultra goth's (#0a0909, #131011),
 * worst neighbouring pair ΔE 8.4 for colour blindness and 19.3 for full colour.
 * Print is the one light surface: there three slots sit under 3:1 on white, so
 * every chart has its table.
 *
 * Charts never use these hex values directly: charts.css sets them as custom
 * properties on `.chart`, per theme, and a mark asks for `series(n)`. Text never
 * wears a series colour; it uses the ink tokens.
 */

/** The categorical slots, in their fixed order: the order is what keeps neighbours apart. */
export const SLOTS = 8;

/** Categorical hues on Horatio's dark surfaces (Dark and Ultra goth alike). */
export const CATEGORICAL_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"] as const;

/** The same hues, stepped for white paper, when a chart is printed. */
export const CATEGORICAL_PRINT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"] as const;

/**
 * One hue for magnitude (a heatmap's cells): the blue ramp's steps 700 to 100. On
 * Horatio's dark surfaces the dark end means "nearly nothing" and sinks into the
 * surface, so it comes first; more is lighter.
 */
export const SEQUENTIAL = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"] as const;

/**
 * Two poles that read as opposite, blue below and red above, and a grey middle
 * that reads as nothing (a net standing of 0). The poles are categorical slots 1
 * and 8 on the dark surface; between them a value is blended in Lab.
 */
export const DIVERGING = { low: "#3987e5", mid: "#383835", high: "#e66767" } as const;

/**
 * How many categorical slots a form of chart can use. Where only neighbours touch
 * (bars, stacks, lines) all eight stay apart; where any two marks can sit side by
 * side (a scatter, a network's nodes, small multiples) only the first three do.
 * Past the cap, the rest fold into "Other".
 */
export const SLOT_CAP = { adjacent: SLOTS, allPairs: 3 } as const;
export type ChartForm = keyof typeof SLOT_CAP;

/** A categorical slot, 1 to 8, or the grey that "Other" is drawn in. */
export type Slot = number | "other";

/** The CSS colour for a slot, from charts.css's custom properties. */
export function series(slot: Slot): string {
  return slot === "other" ? "var(--chart-other)" : `var(--chart-series-${slot})`;
}

const clamp = (t: number) => Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0));

/** A step of the sequential ramp for a value from 0 to 1 (clamped), so cells fall into seven readable classes. */
export function sequential(t: number): string {
  return SEQUENTIAL[Math.round(clamp(t) * (SEQUENTIAL.length - 1))]!;
}

const below = interpolateLab(DIVERGING.mid, DIVERGING.low);
const above = interpolateLab(DIVERGING.mid, DIVERGING.high);

/** A colour for a value from -1 to 1 (clamped): blue below 0, grey at 0, red above. */
export function diverging(t: number): string {
  const v = Math.min(1, Math.max(-1, Number.isFinite(t) ? t : 0));
  return v < 0 ? below(-v) : above(v);
}
