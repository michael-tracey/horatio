/**
 * Horatio's chart kit (#706): the pieces every chart is built from, on d3's
 * modules. Import it only from a page loaded with `lazy()`, never from the app's
 * first chunk or the Play View: d3 goes in a chunk of its own (vite.config.ts),
 * kept out of the offline cache, and `npm run build` fails if it reaches the
 * first chunk (scripts/check-chart-chunks.mjs).
 *
 * - ChartFrame: the card, title and description, legend, plot, table view,
 *   loading and empty states. plotArea: the plot inside the axes' margins.
 * - AxisBottom, AxisLeft: hairline axes and gridlines, labels in the secondary ink.
 * - Legend: swatches and names, optionally toggling series.
 * - useMarks: hover, focus and tap tooltips for marks; Tip is what they say.
 * - useZoom, ZoomControls: zoom and pan.
 * - series, sequential, diverging: colours by job; assignSlots and clanSlots
 *   give things stable categorical slots, folding the rest into "Other".
 * - formatValue, tickFormat: numbers as charts show them.
 * - useReducedMotion, useWidth.
 */
export { AxisBottom, AxisLeft, ticksOf } from "./Axis";
export { assignSlots, slotOf } from "./categorical";
export { ChartFrame, plotArea, TableView, type ChartTable, type Plot } from "./ChartFrame";
export { clanKey, clanSlots, NO_CLAN } from "./clans";
export { formatValue, tickFormat } from "./format";
export { useReducedMotion, useWidth } from "./hooks";
export { Legend, type LegendItem } from "./Legend";
export { diverging, sequential, series, SLOT_CAP, SLOTS, type ChartForm, type Slot } from "./palette";
export { tipText, useMarks, type Anchor, type Tip } from "./Tooltip";
export { useZoom, ZoomControls } from "./zoom";
