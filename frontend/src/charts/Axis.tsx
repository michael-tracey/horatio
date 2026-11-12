import type { ScaleBand, ScaleLinear, ScaleTime } from "d3-scale";
import { tickFormat } from "./format";

type Continuous = ScaleLinear<number, number> | ScaleTime<number, number>;
type AnyScale = Continuous | ScaleBand<string>;

type Tick = { at: number; label: string; key: string };

function isBand(scale: AnyScale): scale is ScaleBand<string> {
  return "bandwidth" in scale;
}

/** Where a scale's ticks fall and what they say: a band's middle and name, or a continuous scale's round values. */
export function ticksOf(scale: AnyScale, count = 5, format?: (v: never) => string): Tick[] {
  if (isBand(scale)) {
    const half = scale.bandwidth() / 2;
    return scale.domain().map((d) => ({ at: (scale(d) ?? 0) + half, label: format ? format(d as never) : d, key: d }));
  }
  const values = scale.ticks(count) as (number | Date)[];
  const largest = Math.max(...values.map((v) => Math.abs(Number(v))), 0);
  const label = format ?? (values[0] instanceof Date ? (scale as ScaleTime<number, number>).tickFormat(count) : tickFormat(largest));
  return values.map((v) => ({ at: scale(v as never) as number, label: (label as (v: number | Date) => string)(v), key: String(Number(v)) }));
}

const TEXT = { fill: "var(--chart-ink-secondary)", fontSize: 11, fontVariantNumeric: "tabular-nums" } as const;

/**
 * The axis along the bottom of a plot, at `y`: a hairline baseline, and its
 * ticks' labels in the secondary ink. Text never wears a series colour.
 */
export function AxisBottom({ scale, y, count, format }: { scale: AnyScale; y: number; count?: number; format?: (v: never) => string }) {
  const [start, end] = scale.range() as [number, number];
  return (
    <g aria-hidden="true">
      <line x1={start} x2={end} y1={y + 0.5} y2={y + 0.5} stroke="var(--chart-axis)" strokeWidth={1} />
      {ticksOf(scale, count, format).map((t) => (
        <text key={t.key} x={t.at} y={y + 16} textAnchor="middle" style={TEXT}>
          {t.label}
        </text>
      ))}
    </g>
  );
}

/**
 * The axis down the left of a plot, at `x`, with its labels. Given `grid` (the
 * plot's width), each tick also draws a solid hairline gridline across it,
 * recessive, in the grid colour.
 */
export function AxisLeft({ scale, x, grid, count, format }: { scale: AnyScale; x: number; grid?: number; count?: number; format?: (v: never) => string }) {
  return (
    <g aria-hidden="true">
      {ticksOf(scale, count, format).map((t) => (
        <g key={t.key}>
          {grid !== undefined && !isBand(scale) && <line x1={x} x2={x + grid} y1={Math.round(t.at) + 0.5} y2={Math.round(t.at) + 0.5} stroke="var(--chart-grid)" strokeWidth={1} />}
          <text x={x - 8} y={t.at} dy="0.32em" textAnchor="end" style={TEXT}>
            {t.label}
          </text>
        </g>
      ))}
    </g>
  );
}
