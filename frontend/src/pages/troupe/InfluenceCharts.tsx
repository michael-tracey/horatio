import { useQuery } from "@tanstack/react-query";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import { scaleBand, scaleLinear, scaleSqrt } from "d3-scale";
import { useMemo, useState, type KeyboardEvent } from "react";
import { api, unwrap } from "../../api/client";
import type { ChartCycleOut, ChartEntryOut } from "../../api/types";
import { AxisBottom, AxisLeft, ChartFrame, formatValue, Legend, plotArea, sequential, series, useMarks, useZoom, ZoomControls, type ChartTable } from "../../charts";
import { ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { TYPE_NAMES } from "../../influence";
import {
  conflictWeb,
  heatmap,
  holdingsTree,
  monthLabel,
  perCycle,
  type HeatCell,
  type HoldingGroup,
  type HoldingLeaf,
  type LinkKind,
  type Measure,
  type TypeChoice,
  type WebNode,
} from "./influenceCharts";

/*
 * The influence log as charts (#710), for the staff who keep the log: a heatmap
 * of actions by specialisation and month, a web of who aimed conflict actions at
 * whom, who holds what influence now, and actions in each downtime cycle. Loaded
 * lazily, so d3 stays out of the rest of the troupe's pages.
 */

type Range = "year" | "all";

/** Elite and Underworld keep the same colour in every chart on this page. */
const TYPE_SLOT = { elite: 1, underworld: 2 } as const;

/** The first of the month eleven months ago, so "the last 12 months" includes this one. */
function yearAgo(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 11, 1)).toISOString();
}

function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-ash text-sm">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`min-h-9 px-3 ${value === o.value ? "bg-ash text-parchment" : "text-mist hover:text-parchment"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function InfluenceCharts({ troupeId }: { troupeId: string }) {
  const [type, setType] = useState<TypeChoice>("both");
  const [range, setRange] = useState<Range>("year");
  const since = useMemo(() => (range === "year" ? yearAgo() : undefined), [range]);
  const path = { troupe_id: troupeId };
  const charts = useQuery({
    queryKey: ["influence-charts", troupeId, since],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-charts", { params: { path, query: { since } } })),
    placeholderData: (previous) => previous,
  });
  const holdings = useQuery({
    queryKey: ["influence-holdings", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-charts/holdings", { params: { path } })),
  });
  const entries = charts.data?.entries ?? [];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Choice
          label="Influence"
          value={type}
          onChange={setType}
          options={[
            { value: "both", label: "Both" },
            { value: "elite", label: "Elite" },
            { value: "underworld", label: "Underworld" },
          ]}
        />
        <Choice
          label="Period"
          value={range}
          onChange={setRange}
          options={[
            { value: "year", label: "Last 12 months" },
            { value: "all", label: "All time" },
          ]}
        />
      </div>
      {charts.error && <ErrorText error={charts.error} />}
      <Heat entries={entries} type={type} loading={charts.isPending} refreshing={charts.isPlaceholderData} />
      <div className="grid gap-4 lg:grid-cols-2">
        <ConflictWeb entries={entries} type={type} loading={charts.isPending} />
        <Cycles entries={entries} cycles={charts.data?.cycles ?? []} type={type} loading={charts.isPending} />
      </div>
      {holdings.error && <ErrorText error={holdings.error} />}
      <Holdings groups={holdingsTree(holdings.data?.holdings ?? [], type).children} loading={holdings.isPending} />
    </div>
  );
}

// --- heatmap ---------------------------------------------------------------------------

/** Mark props that also pick the mark with a click, Enter or Space. */
function picking(props: ReturnType<ReturnType<typeof useMarks>>, pick: () => void) {
  return {
    ...props,
    onClick: () => {
      props.onClick();
      pick();
    },
    onKeyDown: (e: KeyboardEvent<SVGElement>) => {
      props.onKeyDown(e);
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pick();
      }
    },
  };
}

const truncate = (text: string, length: number) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

function Heat({ entries, type, loading, refreshing }: { entries: ChartEntryOut[]; type: TypeChoice; loading: boolean; refreshing: boolean }) {
  const mark = useMarks();
  const [measure, setMeasure] = useState<Measure>("actions");
  const [picked, setPicked] = useState<{ row: string; month: string } | null>(null);
  const map = useMemo(() => heatmap(entries, type, measure), [entries, type, measure]);
  const cells = new Map(map.cells.map((c) => [`${c.row}@${c.month}`, c]));
  const chosen = picked ? cells.get(`${picked.row}@${picked.month}`) : undefined;
  const label = new Map(map.rows.map((r) => [r.key, r.label]));
  const unit = measure === "actions" ? "actions" : "levels";
  const table: ChartTable = {
    columns: [{ key: "spec", label: "Specialisation" }, ...map.months.map((m) => ({ key: m, label: monthLabel(m), numeric: true })), { key: "total", label: "Total", numeric: true }],
    rows: map.rows.map((r) => ({
      spec: r.label,
      ...Object.fromEntries(map.months.map((m) => [m, cells.get(`${r.key}@${m}`)?.value ?? 0])),
      total: r.total,
    })),
  };
  return (
    <>
      <ChartFrame
        title="Actions by specialisation and month"
        description={
          measure === "actions"
            ? "Each cell is how many actions were taken in that specialisation that month: lighter is more. Select a cell to see its entries."
            : "Each cell adds up the levels of the general actions taken: lighter is more. Conflict actions have no level, so they aren't counted here."
        }
        height={Math.max(120, map.rows.length * 24 + 36)}
        table={table}
        state={loading ? "loading" : map.rows.length ? "ready" : "empty"}
        empty="No influence actions logged in this period."
        refreshing={refreshing}
        controls={
          <Choice
            label="Count"
            value={measure}
            onChange={setMeasure}
            options={[
              { value: "actions", label: "Actions" },
              { value: "levels", label: "By level" },
            ]}
          />
        }
      >
        {({ width, height }) => {
          const labelWidth = Math.min(150, Math.max(90, width * 0.28));
          const p = plotArea(width, height, { left: labelWidth, top: 4, right: 4, bottom: 28 });
          const x = scaleBand(map.months, [p.left, p.left + p.width]).paddingInner(map.months.length > 40 ? 0 : 0.08);
          const y = scaleBand(
            map.rows.map((r) => r.key),
            [p.top, p.top + p.height],
          ).paddingInner(0.08);
          // Thin the month labels so they never collide: about 44px each.
          const every = Math.max(1, Math.ceil((map.months.length * 44) / Math.max(1, p.width)));
          return (
            <>
              <AxisLeft scale={y} x={p.left} format={(k: string) => truncate(label.get(k) ?? k, Math.floor(labelWidth / 6.5))} />
              {map.rows.flatMap((r) =>
                map.months.map((m) => {
                  const cell: HeatCell | undefined = cells.get(`${r.key}@${m}`);
                  const value = cell?.value ?? 0;
                  const cx = x(m) ?? 0;
                  const cy = y(r.key) ?? 0;
                  const isPicked = picked?.row === r.key && picked.month === m;
                  const tip = { title: `${r.label}, ${monthLabel(m)}`, rows: [{ label: unit, value: formatValue(value) }] };
                  return (
                    <g key={`${r.key}@${m}`} {...picking(mark(tip, { x: cx + x.bandwidth() / 2, y: cy }), () => setPicked(cell ? { row: r.key, month: m } : null))} data-cell={`${r.label} ${m}`}>
                      <rect
                        x={cx}
                        y={cy}
                        width={Math.max(1, x.bandwidth())}
                        height={y.bandwidth()}
                        rx={2}
                        fill={value > 0 ? sequential(value / map.max) : "transparent"}
                        stroke={isPicked ? "var(--chart-ink)" : value > 0 ? "none" : "var(--chart-grid)"}
                        strokeWidth={isPicked ? 2 : 1}
                        strokeOpacity={value > 0 || isPicked ? 1 : 0.5}
                      />
                    </g>
                  );
                }),
              )}
              <AxisBottom scale={x} y={p.top + p.height} format={(m: string) => (map.months.indexOf(m) % every ? "" : monthLabel(m))} />
            </>
          );
        }}
      </ChartFrame>
      {chosen && <CellEntries cell={chosen} label={label.get(chosen.row) ?? ""} onClose={() => setPicked(null)} />}
    </>
  );
}

function CellEntries({ cell, label, onClose }: { cell: HeatCell; label: string; onClose: () => void }) {
  const dates = useDates();
  return (
    <section aria-label={`Entries for ${label}, ${monthLabel(cell.month)}`} className="rounded-lg border border-ash bg-dusk p-4">
      <header className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-base text-gold">
          {label}, {monthLabel(cell.month)}
        </h3>
        <button type="button" onClick={onClose} className="min-h-8 text-sm text-mist underline hover:text-parchment">
          Close
        </button>
      </header>
      <ul className="divide-y divide-ash/60 text-sm">
        {cell.entries.map((e) => (
          <li key={e.id} className="flex flex-wrap gap-x-3 py-1.5">
            <span className="font-mono text-mist">{e.short_id}</span>
            <span className="text-mist">{dates.dateTime(e.happened_at)}</span>
            <span className="text-parchment">{e.name}</span>
            <span>
              {e.action}
              {e.times > 1 ? ` ×${e.times}` : ""}
            </span>
            {e.purpose && <span className="w-full text-mist">{e.purpose}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- conflict web ----------------------------------------------------------------------

const KIND_SLOT: Record<LinkKind, number> = { against: 2, support: 1, block: 3 };
const KIND_NAMES: Record<LinkKind, string> = { against: "Attack", support: "Boost or Defend", block: "Block" };

type Placed = SimulationNodeDatum & WebNode;

function ConflictWeb({ entries, type, loading }: { entries: ChartEntryOut[]; type: TypeChoice; loading: boolean }) {
  const mark = useMarks();
  const zoom = useZoom();
  const web = useMemo(() => conflictWeb(entries, type), [entries, type]);
  // Laid out once per web, in a unit square, then scaled to the card: a still picture, not a moving one.
  const placed = useMemo(() => {
    const nodes: Placed[] = web.nodes.map((n) => ({ ...n }));
    const links = web.links.map((l) => ({ ...l }));
    const simulation = forceSimulation(nodes)
      .force("charge", forceManyBody().strength(-60))
      .force("link", forceLink<Placed, (typeof links)[number]>(links).id((n) => n.key).distance(60))
      .force("collide", forceCollide(18))
      .force("x", forceX(0).strength(0.05))
      .force("y", forceY(0).strength(0.05))
      .stop();
    for (let i = 0; i < 300; i += 1) simulation.tick();
    return new Map(nodes.map((n) => [n.key, n]));
  }, [web]);
  const kinds = (["against", "support", "block"] as const).filter((k) => web.links.some((l) => l.kind === k));
  const table: ChartTable = {
    columns: [
      { key: "from", label: "From" },
      { key: "kind", label: "Action" },
      { key: "to", label: "At" },
      { key: "times", label: "Times", numeric: true },
      { key: "specs", label: "Specialisations" },
    ],
    rows: web.links.map((l) => ({
      from: placed.get(l.source)?.name ?? "",
      kind: KIND_NAMES[l.kind],
      to: placed.get(l.target)?.name ?? "",
      times: l.weight,
      specs: l.specializations.join(", "),
    })),
  };
  const many = web.nodes.length > 30;
  return (
    <ChartFrame
      title="Who acts against whom"
      description="Conflict actions as a web: an arrow from whoever took it to whom it was aimed at, thicker for more. A square is an activity a Block is on. Select someone for their totals."
      height={360}
      table={table}
      state={loading ? "loading" : web.links.length ? "ready" : "empty"}
      empty="No Attacks, Boosts, Defends or Blocks aimed at anyone in this period."
      svgRef={zoom.ref}
      controls={<ZoomControls zoom={zoom} />}
      legend={kinds.length > 1 ? <Legend items={kinds.map((k) => ({ key: k, label: KIND_NAMES[k], colour: series(KIND_SLOT[k]), mark: "line" as const }))} /> : undefined}
    >
      {({ width, height }) => {
        const all = [...placed.values()];
        const xs = all.map((n) => n.x ?? 0);
        const ys = all.map((n) => n.y ?? 0);
        const pad = 28;
        const x = scaleLinear([Math.min(...xs), Math.max(...xs) || 1], [pad, width - pad]);
        const y = scaleLinear([Math.min(...ys), Math.max(...ys) || 1], [pad, height - pad]);
        const at = (n: Placed) => ({ x: zoom.transform.applyX(x(n.x ?? 0)), y: zoom.transform.applyY(y(n.y ?? 0)) });
        const maxWeight = Math.max(...web.links.map((l) => l.weight), 1);
        const stroke = scaleSqrt([1, maxWeight], [1.5, 5]);
        const size = scaleSqrt([0, Math.max(...all.map((n) => n.in + n.out), 1)], [5, 14]);
        return (
          <>
            <defs>
              {kinds.map((k) => (
                <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M0,0L10,5L0,10z" fill={series(KIND_SLOT[k])} />
                </marker>
              ))}
            </defs>
            <rect x={0} y={0} width={width} height={height} fill="transparent" />
            {web.links.map((l) => {
              const s = placed.get(l.source)!;
              const t = placed.get(l.target)!;
              const a = at(s);
              const b = at(t);
              // Stop the arrow at the target's edge.
              const dx = b.x - a.x;
              const dy = b.y - a.y;
              const len = Math.hypot(dx, dy) || 1;
              const r = size(t.in + t.out) + 3;
              const tip = {
                title: `${s.name} → ${t.name}`,
                rows: [
                  { label: KIND_NAMES[l.kind].toLowerCase(), value: formatValue(l.weight), colour: series(KIND_SLOT[l.kind]) },
                  ...(l.specializations.length ? [{ label: "over", value: l.specializations.join(", ") }] : []),
                ],
              };
              return (
                <g key={`${l.source}>${l.target}>${l.kind}`} {...mark(tip, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 })}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={12} />
                  <line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x - (dx / len) * r}
                    y2={b.y - (dy / len) * r}
                    stroke={series(KIND_SLOT[l.kind])}
                    strokeWidth={stroke(l.weight)}
                    strokeOpacity={0.85}
                    markerEnd={`url(#arrow-${l.kind})`}
                  />
                </g>
              );
            })}
            {all.map((n) => {
              const p = at(n);
              const r = size(n.in + n.out);
              const tip = {
                title: n.name,
                rows: [
                  ...(n.kind === "activity" ? [] : [{ label: "aimed at others", value: formatValue(n.out) }]),
                  { label: n.kind === "activity" ? "Blocks on it" : "aimed at them", value: formatValue(n.in) },
                  ...(n.discovery ? [{ label: "discovery blocks", value: formatValue(n.discovery) }] : []),
                ],
              };
              return (
                <g key={n.key} {...mark(tip, p)}>
                  <circle cx={p.x} cy={p.y} r={r + 6} fill="transparent" />
                  {n.kind === "activity" ? (
                    <rect x={p.x - r} y={p.y - r} width={r * 2} height={r * 2} rx={2} fill="var(--chart-surface)" stroke="var(--chart-ink-secondary)" strokeWidth={2} />
                  ) : (
                    <circle cx={p.x} cy={p.y} r={r} fill="var(--chart-other)" stroke="var(--chart-surface)" strokeWidth={2} />
                  )}
                  {(!many || n.in + n.out >= 3) && (
                    <text x={p.x} y={p.y + r + 12} textAnchor="middle" style={{ fill: "var(--chart-ink-secondary)", fontSize: 11 }} pointerEvents="none">
                      {truncate(n.name, 22)}
                    </text>
                  )}
                </g>
              );
            })}
          </>
        );
      }}
    </ChartFrame>
  );
}

// --- actions per cycle -----------------------------------------------------------------

/** A column whose data end is rounded and whose baseline end is square. */
function columnPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0) return "";
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function Cycles({ entries, cycles, type, loading }: { entries: ChartEntryOut[]; cycles: ChartCycleOut[]; type: TypeChoice; loading: boolean }) {
  const mark = useMarks();
  const found = useMemo(() => perCycle(entries, cycles), [entries, cycles]);
  const types = type === "both" ? (["elite", "underworld"] as const) : ([type] as const);
  const rows = found.rows.filter((r) => types.some((t) => r[t] > 0));
  const table: ChartTable = {
    columns: [{ key: "cycle", label: "Cycle" }, ...types.map((t) => ({ key: t, label: TYPE_NAMES[t], numeric: true }))],
    rows: rows.map((r) => ({ cycle: r.name, ...Object.fromEntries(types.map((t) => [t, r[t]])) })),
  };
  const outside = !found.outside ? "" : cycles.length ? ` ${found.outside} taken since the last cycle closed aren't shown.` : ` ${found.outside} taken outside any cycle aren't shown.`;
  return (
    <ChartFrame
      title="Actions in each downtime cycle"
      description={`Actions taken in each cycle, by type, oldest first. One logged without a cycle counts in the cycle it fell in.${outside}`}
      height={240}
      table={table}
      state={loading ? "loading" : rows.length ? "ready" : "empty"}
      empty="No actions in any downtime cycle in this period."
      legend={types.length > 1 ? <Legend items={types.map((t) => ({ key: t, label: TYPE_NAMES[t], colour: series(TYPE_SLOT[t]) }))} /> : undefined}
    >
      {({ width, height }) => {
        const p = plotArea(width, height, { left: 36, top: 18 });
        const x = scaleBand(
          rows.map((r) => r.id),
          [p.left, p.left + p.width],
        ).padding(0.25);
        const inner = scaleBand(types, [0, x.bandwidth()]).paddingInner(0.1);
        const y = scaleLinear([0, Math.max(1, ...rows.flatMap((r) => types.map((t) => r[t])))], [p.top + p.height, p.top]).nice();
        const name = new Map(rows.map((r) => [r.id, r.name]));
        const every = Math.max(1, Math.ceil((rows.length * 70) / Math.max(1, p.width)));
        return (
          <>
            <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
            {rows.flatMap((r) =>
              types.map((t) => {
                const w = Math.min(24, inner.bandwidth());
                const cx = (x(r.id) ?? 0) + (inner(t) ?? 0) + inner.bandwidth() / 2;
                const top = y(r[t]);
                const tip = { title: r.name, rows: [{ label: `${TYPE_NAMES[t]} actions`, value: formatValue(r[t]), colour: series(TYPE_SLOT[t]) }] };
                return (
                  <g key={`${r.id}-${t}`} {...mark(tip, { x: cx, y: top })}>
                    <rect x={cx - inner.bandwidth() / 2} y={p.top} width={inner.bandwidth()} height={p.height} fill="transparent" />
                    <path d={columnPath(cx - w / 2, top, w, y(0) - top)} fill={series(TYPE_SLOT[t])} />
                  </g>
                );
              }),
            )}
            <AxisBottom scale={x} y={p.top + p.height} format={(id: string) => (rows.findIndex((r) => r.id === id) % every ? "" : truncate(name.get(id) ?? "", 12))} />
          </>
        );
      }}
    </ChartFrame>
  );
}

// --- who holds what --------------------------------------------------------------------

type Tree = { name: string; children?: (HoldingGroup | HoldingLeaf)[] };

function Holdings({ groups, loading }: { groups: HoldingGroup[]; loading: boolean }) {
  const mark = useMarks();
  const table: ChartTable = {
    columns: [
      { key: "type", label: "Influence" },
      { key: "name", label: "Character" },
      { key: "rating", label: "Rating", numeric: true },
      { key: "specs", label: "Specialisations" },
    ],
    rows: groups.flatMap((g) => g.children.map((c) => ({ type: g.name, name: c.name, rating: c.rating, specs: c.specializations.join(", ") }))),
  };
  const both = groups.length > 1;
  return (
    <ChartFrame
      title="Who holds what"
      description="Each character's influence rating now, as an area: larger holds more. Their own specialisations are in each one's details."
      height={300}
      table={table}
      state={loading ? "loading" : groups.length ? "ready" : "empty"}
      empty="Nobody in the troupe holds any influence."
      legend={both ? <Legend items={groups.map((g) => ({ key: g.type, label: g.name, colour: series(TYPE_SLOT[g.type]) }))} /> : undefined}
    >
      {({ width, height }) => {
        const root = hierarchy<Tree | HoldingLeaf>({ name: "Influence", children: groups } as Tree, (d) => ("children" in d ? d.children : undefined))
          .sum((d) => ("rating" in d ? d.rating : 0))
          .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
        treemap<Tree | HoldingLeaf>().tile(treemapSquarify).size([width, height]).paddingInner(2).paddingOuter(0).paddingTop((d) => (both && d.depth === 1 ? 18 : 0))(root);
        const leaves = root.leaves() as unknown as { x0: number; y0: number; x1: number; y1: number; data: HoldingLeaf }[];
        const tops = both ? (root.children ?? []) : [];
        return (
          <>
            {(tops as unknown as { x0: number; y0: number; x1: number; data: HoldingGroup }[]).map((g) => (
              <text key={g.data.type} x={g.x0 + 2} y={g.y0 + 12} style={{ fill: "var(--chart-ink-secondary)", fontSize: 11 }}>
                {truncate(g.data.name, Math.floor((g.x1 - g.x0) / 7))}
              </text>
            ))}
            {leaves.map((l) => {
              const w = l.x1 - l.x0;
              const h = l.y1 - l.y0;
              const leaf = l.data;
              const tip = {
                title: leaf.name,
                rows: [
                  { label: TYPE_NAMES[leaf.type], value: formatValue(leaf.rating), colour: series(TYPE_SLOT[leaf.type]) },
                  ...(leaf.specializations.length ? [{ label: "specialisations", value: leaf.specializations.join(", ") }] : []),
                ],
              };
              return (
                <g key={`${leaf.type}-${leaf.characterId}`} {...mark(tip, { x: l.x0 + w / 2, y: l.y0 })}>
                  <rect x={l.x0} y={l.y0} width={Math.max(0, w)} height={Math.max(0, h)} rx={4} fill={series(TYPE_SLOT[leaf.type])} />
                  {w > 56 && h > 30 && (
                    <text x={l.x0 + 6} y={l.y0 + 16} pointerEvents="none" style={{ fill: "#0b0b0b", fontSize: 12 }}>
                      {truncate(leaf.name, Math.floor((w - 24) / 7))} {leaf.rating}
                    </text>
                  )}
                </g>
              );
            })}
          </>
        );
      }}
    </ChartFrame>
  );
}

