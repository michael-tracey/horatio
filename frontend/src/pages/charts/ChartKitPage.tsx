import { scaleBand, scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useMemo, useState } from "react";
import {
  AxisBottom,
  AxisLeft,
  ChartFrame,
  clanSlots,
  diverging,
  formatValue,
  Legend,
  plotArea,
  sequential,
  series,
  slotOf,
  useMarks,
  useZoom,
  ZoomControls,
  type ChartTable,
} from "../../charts";
import { clanNamed } from "../../clanNames";
import { PageTitle } from "../../components/ui";

/*
 * The chart kit's demonstration (#706): each piece, drawn with made-up sample
 * data, so its look can be checked in every theme and on a phone before a real
 * chart uses it. Nothing here comes from a troupe.
 */

/** A column whose data end is rounded (4px) and whose baseline end is square. */
function columnPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0) return "";
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

/** A bar growing right from the baseline, rounded at its data end. */
function barPath(x: number, y: number, w: number, h: number): string {
  if (w <= 0) return "";
  const r = Math.min(4, w, h / 2);
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
}

const TYPES = [
  { type: "Trivial", open: 38 },
  { type: "Minor", open: 70 },
  { type: "Major", open: 17 },
  { type: "Blood", open: 2 },
  { type: "Life", open: 0 },
];

function Columns() {
  const mark = useMarks();
  const table: ChartTable = { columns: [{ key: "type", label: "Type" }, { key: "open", label: "Open", numeric: true }], rows: TYPES };
  return (
    <ChartFrame title="Open boons by type" description="Sample data: one series, so no legend; each column's value sits on its cap." height={220} table={table}>
      {({ width, height }) => {
        const p = plotArea(width, height, { left: 36, top: 18 });
        const x = scaleBand(
          TYPES.map((t) => t.type),
          [p.left, p.left + p.width],
        ).padding(0.3);
        const y = scaleLinear([0, Math.max(...TYPES.map((t) => t.open))], [p.top + p.height, p.top]).nice();
        const w = Math.min(24, x.bandwidth());
        return (
          <>
            <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
            {TYPES.map((t) => {
              const cx = (x(t.type) ?? 0) + x.bandwidth() / 2;
              const top = y(t.open);
              return (
                <g key={t.type} {...mark({ title: t.type, rows: [{ label: "open", value: formatValue(t.open) }] }, { x: cx, y: top })}>
                  <rect x={cx - x.bandwidth() / 2} y={p.top} width={x.bandwidth()} height={p.height} fill="transparent" />
                  <path d={columnPath(cx - w / 2, top, w, y(0) - top)} fill={series(1)} />
                  <text x={cx} y={top - 6} textAnchor="middle" style={{ fill: "var(--chart-ink)", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                    {formatValue(t.open)}
                  </text>
                </g>
              );
            })}
            <AxisBottom scale={x} y={p.top + p.height} />
          </>
        );
      }}
    </ChartFrame>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const REGISTERED = [21, 34, 29, 40, 38, 52, 47, 44, 39, 58, 61, 49];
const SETTLED = [4, 9, 12, 10, 14, 18, 11, 16, 13, 20, 17, 22];
const LINES = [
  { key: "registered", label: "Registered", values: REGISTERED, slot: 1 },
  { key: "settled", label: "Settled", values: SETTLED, slot: 2 },
];

function Lines() {
  const mark = useMarks();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const shown = LINES.filter((l) => !hidden.has(l.key));
  const table: ChartTable = {
    columns: [{ key: "month", label: "Month" }, ...LINES.map((l) => ({ key: l.key, label: l.label, numeric: true }))],
    rows: MONTHS.map((month, i) => ({ month, registered: REGISTERED[i]!, settled: SETTLED[i]! })),
  };
  const toggle = (key: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return (
    <ChartFrame
      title="Boons by month"
      description="Sample data: two series, a legend that hides either, and a crosshair that reads every series at the month pointed at."
      height={240}
      table={table}
      legend={<Legend items={LINES.map((l) => ({ key: l.key, label: l.label, colour: series(l.slot), mark: "line" }))} hidden={hidden} onToggle={toggle} />}
    >
      {({ width, height }) => {
        const p = plotArea(width, height, { left: 36, top: 12 });
        const x = scaleBand(MONTHS, [p.left, p.left + p.width]);
        const y = scaleLinear([0, Math.max(...REGISTERED)], [p.top + p.height, p.top]).nice();
        const at = (i: number) => (x(MONTHS[i]!) ?? 0) + x.bandwidth() / 2;
        const path = line<number>()
          .x((_, i) => at(i))
          .y((v) => y(v));
        return (
          <>
            <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
            {shown.map((l) => (
              <g key={l.key} pointerEvents="none">
                <path d={path(l.values) ?? ""} fill="none" stroke={series(l.slot)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                <circle cx={at(MONTHS.length - 1)} cy={y(l.values.at(-1)!)} r={4} fill={series(l.slot)} stroke="var(--chart-surface)" strokeWidth={2} />
              </g>
            ))}
            {MONTHS.map((month, i) => (
              <g
                key={month}
                {...mark({ title: month, rows: shown.map((l) => ({ label: l.label, value: formatValue(l.values[i]!), colour: series(l.slot) })) }, { x: at(i), y: p.top + 8 })}
              >
                <rect x={x(month)} y={p.top} width={x.bandwidth()} height={p.height} fill="transparent" />
                <line className="chart-crosshair" x1={at(i)} x2={at(i)} y1={p.top} y2={p.top + p.height} stroke="var(--chart-axis)" strokeWidth={1} />
              </g>
            ))}
            <AxisBottom scale={x} y={p.top + p.height} format={(m: string) => (width < 420 && MONTHS.indexOf(m) % 3 ? "" : m)} />
          </>
        );
      }}
    </ChartFrame>
  );
}

/** A made-up troupe's clans: nine, so the eighth slot becomes "Other". */
const TROUPE = [
  { clan: "Tremere", count: 11 },
  { clan: "Ventrue", count: 11 },
  { clan: "Malkavian", count: 10 },
  { clan: "Nosferatu: Creeps", count: 1 },
  { clan: "Nosferatu", count: 9 },
  { clan: "Brujah", count: 10 },
  { clan: "Gangrel", count: 8 },
  { clan: "Toreador", count: 8 },
  { clan: "Lasombra", count: 6 },
  { clan: "Assamite", count: 4 },
];

function Clans() {
  const mark = useMarks();
  const slots = useMemo(() => clanSlots(TROUPE), []);
  const rows = [...slots.keys()].map((clan) => ({
    clan,
    name: clanNamed(clan, "Banu Haqim"),
    count: TROUPE.filter((t) => t.clan.split(":")[0] === clan).reduce((n, t) => n + t.count, 0),
    slot: slotOf(slots, clan),
  }));
  const table: ChartTable = {
    columns: [
      { key: "name", label: "Clan" },
      { key: "count", label: "Characters", numeric: true },
      { key: "colour", label: "Colour" },
    ],
    rows: rows.map((r) => ({ name: r.name, count: r.count, colour: r.slot === "other" ? "Other" : `Slot ${r.slot}` })),
  };
  return (
    <ChartFrame
      title="Clan colours"
      description="Sample data: a troupe's clans take the eight slots by how many characters each has, the same in every chart of that troupe. A bloodline counts as its clan; past seven clans, the rest are Other."
      height={rows.length * 26 + 32}
      table={table}
    >
      {({ width, height }) => {
        const p = plotArea(width, height, { left: 92, top: 4, bottom: 24, right: 28 });
        const y = scaleBand(
          rows.map((r) => r.name),
          [p.top, p.top + p.height],
        ).padding(0.25);
        const x = scaleLinear([0, Math.max(...rows.map((r) => r.count))], [p.left, p.left + p.width]).nice();
        const h = Math.min(24, y.bandwidth());
        return (
          <>
            <AxisLeft scale={y} x={p.left} />
            {rows.map((r) => {
              const cy = (y(r.name) ?? 0) + y.bandwidth() / 2;
              const end = x(r.count);
              return (
                <g key={r.clan} {...mark({ title: r.name, rows: [{ label: "characters", value: formatValue(r.count), colour: series(r.slot) }] }, { x: end, y: cy })}>
                  <rect x={p.left} y={cy - y.bandwidth() / 2} width={p.width} height={y.bandwidth()} fill="transparent" />
                  <path d={barPath(p.left, cy - h / 2, end - p.left, h)} fill={series(r.slot)} />
                  <text x={end + 6} y={cy} dy="0.32em" style={{ fill: "var(--chart-ink)", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                    {r.count}
                  </text>
                </g>
              );
            })}
            <AxisBottom scale={x} y={p.top + p.height} count={4} />
          </>
        );
      }}
    </ChartFrame>
  );
}

/** A repeatable scatter of made-up people for the zoom demonstration. */
function people() {
  let seed = 7;
  const next = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const clans = ["Toreador", "Ventrue", "Nosferatu", "Brujah"];
  return Array.from({ length: 36 }, (_, i) => ({ name: `Sample ${i + 1}`, clan: clans[i % clans.length]!, x: next(), y: next() }));
}

function Field() {
  const mark = useMarks();
  const zoom = useZoom();
  const dots = useMemo(people, []);
  // Any two dots can sit side by side, so only three slots stay apart: two clans, then Other.
  const slots = useMemo(() => clanSlots(dots.map((d) => ({ clan: d.clan, count: 1 })), "allPairs"), [dots]);
  const legend = [...new Set([...slots.values()])].map((slot) => ({
    key: String(slot),
    label: [...slots].filter(([, s]) => s === slot).map(([c]) => c).join(", "),
    colour: series(slot),
    mark: "dot" as const,
  }));
  const table: ChartTable = {
    columns: [
      { key: "name", label: "Name" },
      { key: "clan", label: "Clan" },
    ],
    rows: dots.map((d) => ({ name: d.name, clan: d.clan })),
  };
  return (
    <ChartFrame
      title="Zoom and pan"
      description="Sample data: drag to pan, pinch or Ctrl and the wheel to zoom, or use the buttons. Where any two dots can meet, only three colours stay apart: two clans keep their own, and the others share Other."
      height={280}
      table={table}
      svgRef={zoom.ref}
      controls={<ZoomControls zoom={zoom} />}
      legend={<Legend items={legend} />}
    >
      {({ width, height }) => {
        const p = plotArea(width, height, { left: 12, top: 12, bottom: 12, right: 12 });
        const x = scaleLinear([0, 1], [p.left, p.left + p.width]);
        const y = scaleLinear([0, 1], [p.top, p.top + p.height]);
        return (
          <>
            <rect x={0} y={0} width={width} height={height} fill="transparent" />
            {dots.map((d) => {
              const cx = zoom.transform.applyX(x(d.x));
              const cy = zoom.transform.applyY(y(d.y));
              const slot = slotOf(slots, d.clan);
              return (
                <g key={d.name} {...mark({ title: d.name, rows: [{ label: "clan", value: d.clan, colour: series(slot) }] }, { x: cx, y: cy })}>
                  <circle cx={cx} cy={cy} r={12} fill="transparent" />
                  <circle cx={cx} cy={cy} r={4} fill={series(slot)} stroke="var(--chart-surface)" strokeWidth={2} />
                </g>
              );
            })}
          </>
        );
      }}
    </ChartFrame>
  );
}

const STEPS = Array.from({ length: 7 }, (_, i) => i / 6);
const POLES = Array.from({ length: 9 }, (_, i) => (i - 4) / 4);

function Scales() {
  const mark = useMarks();
  const table: ChartTable = {
    columns: [
      { key: "scale", label: "Scale" },
      { key: "value", label: "Value", numeric: true },
    ],
    rows: [...STEPS.map((v) => ({ scale: "Sequential", value: formatValue(v) })), ...POLES.map((v) => ({ scale: "Diverging", value: formatValue(v) }))],
  };
  return (
    <ChartFrame title="Sequential and diverging" description="How much, in one hue (darker is less); and which side of nothing, blue below, grey at nothing, red above." height={88} table={table}>
      {({ width }) => {
        const cell = (n: number) => Math.max(8, Math.min(40, (width - 100) / n));
        const row = (label: string, y: number, values: number[], colour: (v: number) => string) => (
          <g>
            <text x={0} y={y + 12} dy="0.32em" style={{ fill: "var(--chart-ink-secondary)", fontSize: 11 }}>
              {label}
            </text>
            {values.map((v, i) => (
              <rect key={i} {...mark({ title: label, rows: [{ label: "value", value: formatValue(v) }] }, { x: 90 + i * (cell(values.length) + 2) + cell(values.length) / 2, y })} x={90 + i * (cell(values.length) + 2)} y={y} width={cell(values.length)} height={24} rx={4} fill={colour(v)} />
            ))}
          </g>
        );
        return (
          <>
            {row("Sequential", 4, STEPS, sequential)}
            {row("Diverging", 48, POLES, diverging)}
          </>
        );
      }}
    </ChartFrame>
  );
}

export function ChartKitPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageTitle subtitle="The pieces Horatio's charts are built from, drawn with made-up sample data.">Chart kit</PageTitle>
      <div className="grid gap-4 lg:grid-cols-2">
        <Columns />
        <Lines />
        <Clans />
        <Field />
        <Scales />
        <ChartFrame title="Nothing yet" description="A chart with no data says so in its card." height={120} table={{ columns: [], rows: [] }} state="empty" empty="No boons registered yet.">
          {() => null}
        </ChartFrame>
        <ChartFrame title="Loading" description="The first load shows the loader; a refresh keeps the last drawing, faded." height={120} table={{ columns: [], rows: [] }} state="loading">
          {() => null}
        </ChartFrame>
      </div>
    </div>
  );
}
