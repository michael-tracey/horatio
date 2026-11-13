import { useQuery } from "@tanstack/react-query";
import { chordDirected, ribbonArrow, type Chord, type ChordGroup } from "d3-chord";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { scaleBand, scaleLinear } from "d3-scale";
import { arc, area, stack } from "d3-shape";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { BOON_PAGE, KINDS, kindName, type BoonKind } from "../../boons";
import {
  clanOf,
  flowPairs,
  folded,
  network,
  radius,
  readableMinimum,
  timeline,
  trend,
  weightsOf,
  type Flow,
  type GameActivity,
  type Measure,
  type Statistics,
  type StatNode,
} from "../../boonStatistics";
import { net, SCOPES, weight, type Scope } from "../../boonStandings";
import {
  AxisBottom,
  AxisLeft,
  ChartFrame,
  assignSlots,
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
  type Slot,
} from "../../charts";
import { Card, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";

/*
 * Boon statistics (#702), for the troupe's running staff: how the ledger has moved
 * over time, who owes whom, how debt flows between clans and sects, and what each
 * game did. The sums are the standings' (#691); the charts are the chart kit's
 * (#706), with d3 loaded only with this page.
 */

/** Each kind keeps its own categorical slot in every chart here, lightest first. */
const KIND_SLOT: Record<BoonKind, number> = { trivial: 1, minor: 2, major: 3, blood: 4, life: 5 };
const KIND_ITEMS = KINDS.map((k) => ({ key: k.value, label: k.label, colour: series(KIND_SLOT[k.value]), mark: "rect" as const }));

/** A link's colour in the network: how heavy its heaviest kind is, light to dark across the ramp. */
const KIND_STEP: Record<BoonKind, number> = { trivial: 0.35, minor: 0.5, major: 0.7, blood: 0.85, life: 1 };

/** A column whose data end is rounded (4px) and whose baseline end is square. */
function columnPath(x: number, y: number, w: number, h: number, rounded: boolean): string {
  if (h <= 0) return "";
  const r = rounded ? Math.min(4, h, w / 2) : 0;
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-ash text-sm">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`min-h-8 px-2 first:rounded-l-md last:rounded-r-md ${value === o.value ? "bg-ash text-parchment" : "text-mist hover:text-parchment"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- trends --------------------------------------------------------------------------------

const MEASURES: { value: Measure; label: string }[] = [
  { value: "registered", label: "Registered" },
  { value: "settled", label: "Settled" },
  { value: "open", label: "Open debt" },
];

function Trends({ s }: { s: Statistics }) {
  const mark = useMarks();
  const [measure, setMeasure] = useState<Measure>("registered");
  const [weighted, setWeighted] = useState<"count" | "weight">("count");
  const [basis, setBasis] = useState<"entered" | "night">("entered");
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const byNight = measure === "registered" && basis === "night";
  const whole = useMemo(() => trend(byNight ? s.by_night : s.by_entered, measure, weighted === "weight"), [s, measure, weighted, byNight]);
  // The range chosen, or the whole span; a range that no longer fits is dropped.
  const first = whole.periods.findIndex((p) => p.key === from);
  const last = whole.periods.findIndex((p) => p.key === to);
  const start = first >= 0 ? first : 0;
  const end = last >= start ? last : whole.periods.length - 1;
  const periods = whole.periods.slice(start, end + 1);
  const shown = KINDS.filter((k) => !hidden.has(k.value));
  const values = (kind: BoonKind) => whole.byKind[kind].slice(start, end + 1);
  const totals = periods.map((_, i) => shown.reduce((n, k) => n + values(k.value)[i]!, 0));
  const toggle = (key: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const what = weighted === "weight" ? "weight" : "boons";
  const table: ChartTable = {
    columns: [{ key: "period", label: whole.unit === "year" ? "Year" : "Month" }, ...KINDS.map((k) => ({ key: k.value, label: k.label, numeric: true })), { key: "total", label: "All", numeric: true }],
    rows: periods.map((p, i) => ({ period: p.label, ...Object.fromEntries(KINDS.map((k) => [k.value, formatValue(values(k.value)[i]!)])), total: formatValue(whole.totals[start + i]!) })),
  };
  const describe =
    measure === "open"
      ? `What stood at the end of each ${whole.unit}, by kind: open debt over time, by the day each boon went in the ledger.`
      : measure === "settled"
        ? `Boons settled in each ${whole.unit}, by kind, by the day they were settled.`
        : byNight
          ? `Boons registered, by the in-game night each was made, by kind. Settling and open debt go by real days only.`
          : `Boons registered in each ${whole.unit}, by kind, by the day each went in the ledger.`;
  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="What to show" value={measure} options={MEASURES} onChange={setMeasure} />
      <Segmented
        label="Count or weight"
        value={weighted}
        options={[
          { value: "count", label: "Count" },
          { value: "weight", label: "Weight" },
        ]}
        onChange={setWeighted}
      />
      {measure === "registered" && (
        <Segmented
          label="Which date"
          value={basis}
          options={[
            { value: "entered", label: "Day entered" },
            { value: "night", label: "In-game night" },
          ]}
          onChange={setBasis}
        />
      )}
    </div>
  );
  const range = whole.periods.length > 1 && (
    <div className="flex flex-wrap items-center gap-2 text-sm text-mist">
      <label className="flex items-center gap-1">
        From
        <select aria-label="From" className="rounded-md border border-ash bg-night px-1 py-0.5 text-parchment" value={periods[0]?.key ?? ""} onChange={(e) => setFrom(e.target.value)}>
          {whole.periods.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1">
        to
        <select aria-label="To" className="rounded-md border border-ash bg-night px-1 py-0.5 text-parchment" value={periods.at(-1)?.key ?? ""} onChange={(e) => setTo(e.target.value)}>
          {whole.periods.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {(from !== null || to !== null) && (
        <button
          type="button"
          className="underline hover:text-parchment"
          onClick={() => {
            setFrom(null);
            setTo(null);
          }}
        >
          All of it
        </button>
      )}
    </div>
  );
  return (
    <div className="flex flex-col gap-2">
      {controls}
      {range}
      <ChartFrame
        title={measure === "open" ? "Open debt over time" : measure === "settled" ? "Boons settled" : "Boons registered"}
        description={describe}
        height={260}
        table={table}
        state={periods.length === 0 ? "empty" : "ready"}
        empty="No boons registered yet."
        legend={<Legend items={KIND_ITEMS} hidden={hidden} onToggle={toggle} />}
      >
        {({ width, height }) => {
          const p = plotArea(width, height, { left: 40, top: 12 });
          const x = scaleBand(
            periods.map((q) => q.key),
            [p.left, p.left + p.width],
          ).padding(measure === "open" && periods.length > 1 ? 0 : 0.2);
          const y = scaleLinear([0, Math.max(1, ...totals)], [p.top + p.height, p.top]).nice();
          const every = Math.max(1, Math.ceil(periods.length / Math.max(2, Math.floor(p.width / 64))));
          const label = (key: string) => {
            const i = periods.findIndex((q) => q.key === key);
            return i % every ? "" : (periods[i]?.label ?? "");
          };
          const centre = (i: number) => (x(periods[i]!.key) ?? 0) + x.bandwidth() / 2;
          const tipFor = (i: number) => ({
            title: periods[i]!.label,
            rows: [
              ...shown.filter((k) => values(k.value)[i]! > 0).map((k) => ({ label: k.label.toLowerCase(), value: formatValue(values(k.value)[i]!), colour: series(KIND_SLOT[k.value]) })),
              { label: `${what} in all`, value: formatValue(totals[i]!) },
            ],
          });
          // Open debt is an area; with a single period there is no width to fill, so it is a column.
          if (measure === "open" && periods.length > 1) {
            const rows = periods.map((_, i) => Object.fromEntries(shown.map((k) => [k.value, values(k.value)[i]!])) as Record<BoonKind, number>);
            const layers = stack<Record<BoonKind, number>, BoonKind>().keys(shown.map((k) => k.value))(rows);
            const shape = area<[number, number]>()
              .x((_, i) => centre(i))
              .y0((d) => y(d[0]))
              .y1((d) => y(d[1]));
            return (
              <>
                <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
                {layers.map((layer) => (
                  <path
                    key={layer.key}
                    d={shape(layer.map((d) => [d[0], d[1]] as [number, number])) ?? ""}
                    fill={series(KIND_SLOT[layer.key])}
                    fillOpacity={0.85}
                    stroke="var(--chart-surface)"
                    strokeWidth={1}
                    pointerEvents="none"
                  />
                ))}
                {periods.map((q, i) => (
                  <g key={q.key} {...mark(tipFor(i), { x: centre(i), y: y(totals[i]!) })}>
                    <rect x={x(q.key)} y={p.top} width={Math.max(1, x.bandwidth())} height={p.height} fill="transparent" />
                    <line className="chart-crosshair" x1={centre(i)} x2={centre(i)} y1={p.top} y2={p.top + p.height} stroke="var(--chart-axis)" strokeWidth={1} />
                  </g>
                ))}
                <AxisBottom scale={x} y={p.top + p.height} format={label} />
              </>
            );
          }
          const w = Math.max(1, Math.min(28, x.bandwidth()));
          return (
            <>
              <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
              {periods.map((q, i) => {
                const cx = centre(i);
                let base = 0;
                const top = shown.filter((k) => values(k.value)[i]! > 0).at(-1)?.value;
                return (
                  <g key={q.key} {...mark(tipFor(i), { x: cx, y: y(totals[i]!) })}>
                    <rect x={x(q.key)} y={p.top} width={x.bandwidth()} height={p.height} fill="transparent" />
                    {shown.map((k) => {
                      const v = values(k.value)[i]!;
                      if (v <= 0) return null;
                      const y0 = y(base);
                      base += v;
                      const y1 = y(base);
                      // A 2px gap of the surface between stacked segments.
                      return <path key={k.value} d={columnPath(cx - w / 2, y1, w, Math.max(0, y0 - y1 - (k.value === top ? 0 : 2)), k.value === top)} fill={series(KIND_SLOT[k.value])} />;
                    })}
                  </g>
                );
              })}
              <AxisBottom scale={x} y={p.top + p.height} format={label} />
            </>
          );
        }}
      </ChartFrame>
    </div>
  );
}

// --- the network ---------------------------------------------------------------------------

type Placed = SimulationNodeDatum & { node: StatNode; r: number };
type Joined = SimulationLinkDatum<Placed> & { weight: number; count: number; kind: BoonKind; kinds: Record<string, number> };

/** Where each node settles: the force layout run to rest at once, never animated. */
function layout(nodes: StatNode[], links: ReturnType<typeof network>["links"], width: number, height: number) {
  const heaviest = Math.max(0, ...nodes.map((n) => n.owes + n.owed));
  const placed: Placed[] = nodes.map((node, i) => {
    // Start on a circle, in a fixed order, so the same data lays out the same way.
    const angle = (2 * Math.PI * i) / Math.max(1, nodes.length);
    return { node, r: radius(node, heaviest), x: width / 2 + (width / 3) * Math.cos(angle), y: height / 2 + (height / 3) * Math.sin(angle) };
  });
  const at = new Map(placed.map((p) => [p.node.who.key, p]));
  const joined: Joined[] = links.map((l) => ({ source: at.get(l.debtor)!, target: at.get(l.creditor)!, weight: l.shown, count: l.count, kind: l.kind, kinds: l.kinds }));
  const simulation = forceSimulation(placed)
    .force(
      "link",
      forceLink<Placed, Joined>(joined)
        .distance(60)
        .strength((l) => Math.min(1, 0.2 + l.weight / 10)),
    )
    .force("charge", forceManyBody().strength(-90))
    .force("collide", forceCollide<Placed>((p) => p.r + 3))
    .force("centre", forceCenter(width / 2, height / 2))
    .stop();
  for (let i = 0; i < 300; i += 1) simulation.tick();
  // Keep everyone inside the frame.
  for (const p of placed) {
    p.x = Math.min(width - p.r - 4, Math.max(p.r + 4, p.x ?? 0));
    p.y = Math.min(height - p.r - 4, Math.max(p.r + 4, p.y ?? 0));
  }
  return { placed, joined };
}

function Network({ s, troupeId, harpy }: { s: Statistics; troupeId: string; harpy: boolean }) {
  const mark = useMarks();
  const zoom = useZoom();
  const navigate = useNavigate();
  const weights = weightsOf(s);
  const [clan, setClan] = useState<string | null>(null);
  const [sect, setSect] = useState<string | null>(null);
  const [court, setCourt] = useState(false);
  const [kinds, setKinds] = useState<ReadonlySet<BoonKind>>(new Set(KINDS.map((k) => k.value)));
  const [minWeight, setMinWeight] = useState<number>(() => readableMinimum(s.links));
  const [colourBy, setColourBy] = useState<"net" | "clan">("net");
  const [near, setNear] = useState<string | null>(null);
  const clans = useMemo(() => [...new Set(s.nodes.map(clanOf))].sort(), [s.nodes]);
  const sects = useMemo(() => [...new Set(s.nodes.map((n) => n.who.sect).filter((x): x is string => !!x))].sort(), [s.nodes]);
  const shown = useMemo(() => network(s.nodes, s.links, { clan, sect, court, kinds, minWeight }, weights), [s, clan, sect, court, kinds, minWeight, weights]);
  // Where any two nodes can meet, only three clan colours stay apart: two clans and Other.
  const nodeSlots = useMemo(() => clanSlots(s.nodes.filter((n) => n.who.character_id).map((n) => ({ clan: clanOf(n), count: 1 })), "allPairs"), [s.nodes]);
  const widest = Math.max(1, ...s.nodes.map((n) => Math.abs(n.net)));
  const fill = (n: StatNode) => (colourBy === "net" ? diverging(n.net / widest) : series(slotOf(nodeSlots, clanOf(n))));
  const table: ChartTable = {
    columns: [
      { key: "debtor", label: "Owed by" },
      { key: "creditor", label: "Owed to" },
      { key: "boons", label: "Boons", numeric: true },
      { key: "weight", label: "Weight", numeric: true },
    ],
    rows: shown.links.map((l) => ({
      debtor: s.nodes.find((n) => n.who.key === l.debtor)?.who.name ?? "",
      creditor: s.nodes.find((n) => n.who.key === l.creditor)?.who.name ?? "",
      boons: l.count,
      weight: weight(l.shown),
    })),
  };
  const legend =
    colourBy === "net" ? (
      <p className="text-xs text-mist">
        <span className="mr-1 inline-block h-2 w-4 rounded-sm align-middle" style={{ background: diverging(-1) }} /> owes more ·{" "}
        <span className="mx-1 inline-block h-2 w-4 rounded-sm align-middle" style={{ background: diverging(0) }} /> even ·{" "}
        <span className="mx-1 inline-block h-2 w-4 rounded-sm align-middle" style={{ background: diverging(1) }} /> owed more. A circle&apos;s size is everything on its boons; a line runs from
        debtor to creditor, darker for heavier kinds, thicker for more weight.
      </p>
    ) : (
      <Legend items={[...new Set(nodeSlots.values())].map((slot) => ({ key: String(slot), label: slot === "other" ? "Other clans" : [...nodeSlots].filter(([, v]) => v === slot).map(([c]) => c).join(", "), colour: series(slot), mark: "dot" as const }))} />
    );
  const select = "rounded-md border border-ash bg-night px-1 py-0.5 text-parchment";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-mist">
        <label className="flex items-center gap-1">
          Clan
          <select aria-label="Clan" className={select} value={clan ?? ""} onChange={(e) => setClan(e.target.value || null)}>
            <option value="">All</option>
            {clans.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        {sects.length > 1 && (
          <label className="flex items-center gap-1">
            Sect
            <select aria-label="Sect" className={select} value={sect ?? ""} onChange={(e) => setSect(e.target.value || null)}>
              <option value="">All</option>
              {sects.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={court} onChange={(e) => setCourt(e.target.checked)} />
          The court only
        </label>
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">Kinds shown</legend>
          {KINDS.map((k) => (
            <label key={k.value} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={kinds.has(k.value)}
                onChange={(e) =>
                  setKinds((was) => {
                    const next = new Set(was);
                    if (e.target.checked) next.add(k.value);
                    else next.delete(k.value);
                    return next;
                  })
                }
              />
              {k.label}
            </label>
          ))}
        </fieldset>
        <label className="flex items-center gap-1">
          Weight at least
          <input type="number" aria-label="Weight at least" min={0} step={0.5} className={`${select} w-16`} value={minWeight} onChange={(e) => setMinWeight(Math.max(0, Number(e.target.value) || 0))} />
        </label>
        <Segmented
          label="Colour circles by"
          value={colourBy}
          options={[
            { value: "net", label: "Net" },
            { value: "clan", label: "Clan" },
          ]}
          onChange={setColourBy}
        />
      </div>
      <ChartFrame
        title="Who owes whom"
        description={`Open boons between characters: ${shown.nodes.length} people and ${shown.links.length} of ${s.links.length} debts shown. Hover or tap someone to see their debts${harpy ? "" : "; click again to open their boons"}.`}
        height={480}
        table={table}
        state={shown.links.length === 0 ? "empty" : "ready"}
        empty={s.links.length === 0 ? "No open boons yet." : "No debts match these filters."}
        svgRef={zoom.ref}
        controls={<ZoomControls zoom={zoom} />}
        legend={legend}
      >
        {({ width, height }) => <NetworkPlot shown={shown} width={width} height={height} zoom={zoom} mark={mark} fill={fill} near={near} setNear={setNear} onOpen={(n) => !harpy && n.who.character_id && navigate(`/troupes/${troupeId}/boons?character=${n.who.character_id}`)} />}
      </ChartFrame>
    </div>
  );
}

function NetworkPlot({
  shown,
  width,
  height,
  zoom,
  mark,
  fill,
  near,
  setNear,
  onOpen,
}: {
  shown: ReturnType<typeof network>;
  width: number;
  height: number;
  zoom: ReturnType<typeof useZoom>;
  mark: ReturnType<typeof useMarks>;
  fill: (n: StatNode) => string;
  near: string | null;
  setNear: (key: string | null) => void;
  onOpen: (n: StatNode) => void;
}) {
  const { placed, joined } = useMemo(() => layout(shown.nodes, shown.links, width, height), [shown, width, height]);
  const heaviest = Math.max(1, ...joined.map((l) => l.weight));
  const touches = (l: Joined) => near !== null && ((l.source as Placed).node.who.key === near || (l.target as Placed).node.who.key === near);
  const t = zoom.transform;
  return (
    <>
      <rect x={0} y={0} width={width} height={height} fill="transparent" />
      <g transform={t.toString()}>
        <defs>
          <marker id="boon-arrow" viewBox="0 0 8 8" refX={7} refY={4} markerWidth={5} markerHeight={5} orient="auto-start-reverse">
            <path d="M0,0L8,4L0,8Z" fill="var(--chart-axis)" />
          </marker>
        </defs>
        {joined.map((l, i) => {
          const a = l.source as Placed;
          const b = l.target as Placed;
          const dx = (b.x ?? 0) - (a.x ?? 0);
          const dy = (b.y ?? 0) - (a.y ?? 0);
          const length = Math.hypot(dx, dy) || 1;
          // Stop at the creditor's edge, so the arrow shows.
          const x2 = (b.x ?? 0) - (dx / length) * (b.r + 2);
          const y2 = (b.y ?? 0) - (dy / length) * (b.r + 2);
          const lit = touches(l);
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={x2}
              y2={y2}
              stroke={sequential(KIND_STEP[l.kind])}
              strokeWidth={1 + 3 * Math.sqrt(l.weight / heaviest)}
              strokeOpacity={near === null ? 0.7 : lit ? 1 : 0.12}
              markerEnd="url(#boon-arrow)"
              pointerEvents="none"
            />
          );
        })}
        {placed.map((p) => {
          const n = p.node;
          const dim = near !== null && near !== n.who.key && !joined.some((l) => touches(l) && ((l.source as Placed) === p || (l.target as Placed) === p));
          const tip = {
            title: n.who.name,
            rows: [
              { label: "owed to them", value: weight(n.owed) },
              { label: "they owe", value: weight(n.owes) },
              { label: "net", value: net(n.net) },
              ...(n.who.clan ? [{ label: "clan", value: clanOf(n) }] : []),
              ...(n.who.titles.length ? [{ label: "title", value: n.who.titles.join(", ") }] : []),
            ],
          };
          const handlers = mark(tip, { x: t.applyX(p.x ?? 0), y: t.applyY((p.y ?? 0) - p.r) });
          return (
            <g
              key={n.who.key}
              {...handlers}
              onPointerEnter={() => setNear(n.who.key)}
              onPointerLeave={() => {
                setNear(null);
                handlers.onPointerLeave();
              }}
              onFocus={() => {
                setNear(n.who.key);
                handlers.onFocus();
              }}
              onClick={() => {
                if (near === n.who.key && n.who.character_id) onOpen(n);
                setNear(n.who.key);
                handlers.onClick();
              }}
              opacity={dim ? 0.3 : 1}
            >
              <circle cx={p.x} cy={p.y} r={Math.max(p.r, 10)} fill="transparent" />
              <circle cx={p.x} cy={p.y} r={p.r} fill={fill(n)} stroke="var(--chart-surface)" strokeWidth={2} />
              {(p.r > 10 || near === n.who.key) && (
                <text x={p.x} y={(p.y ?? 0) + p.r + 11} textAnchor="middle" style={{ fill: "var(--chart-ink)", fontSize: 11 }} pointerEvents="none">
                  {n.who.name}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </>
  );
}

// --- flow between clans and sects ----------------------------------------------------------

function FlowChart({ s, clanColours }: { s: Statistics; clanColours: Map<string, Slot> }) {
  const mark = useMarks();
  const [by, setBy] = useState<"clan" | "sect">("clan");
  const flow: Flow = useMemo(() => folded(by === "clan" ? s.clan_flow : s.sect_flow), [s, by]);
  const slots = useMemo(() => (by === "clan" ? clanColours : assignSlots(flow.groups)), [by, clanColours, flow.groups]);
  const colour = (group: string) => series(group === "Other" ? "other" : slotOf(slots, group));
  const pairs = flowPairs(flow);
  const table: ChartTable = {
    columns: [
      { key: "from", label: "From" },
      { key: "to", label: "To" },
      { key: "owed", label: "Owed", numeric: true },
      { key: "back", label: "Back", numeric: true },
      { key: "boons", label: "Boons", numeric: true },
    ],
    rows: pairs.map((p) => ({ from: p.from, to: p.to, owed: weight(p.owed), back: weight(p.back), boons: p.boons })),
  };
  const word = by === "clan" ? "clans" : "sects";
  return (
    <div className="flex flex-col gap-2">
      <Segmented
        label="Between"
        value={by}
        options={[
          { value: "clan", label: "Clans" },
          { value: "sect", label: "Sects" },
        ]}
        onChange={setBy}
      />
      <ChartFrame
        title={`Debt between ${word}`}
        description={`Open boons by weight. Each arc is a ${by === "clan" ? "clan" : "sect"}, sized by all it owes and is owed; each ribbon runs from the ${by} that owes to the one owed, in the colour of the one that owes. A ribbon back to its own arc is debt within it.`}
        height={420}
        table={table}
        state={pairs.length === 0 ? "empty" : "ready"}
        empty="No open boons yet."
        legend={<Legend items={flow.groups.map((g) => ({ key: g, label: g, colour: colour(g), mark: "rect" as const }))} />}
      >
        {({ width, height }) => {
          const outer = Math.max(40, Math.min(width, height) / 2 - 28);
          const inner = outer - 12;
          const chords = chordDirected().padAngle(0.03).sortSubgroups((a, b) => b - a)(flow.matrix);
          const groupArc = arc<ChordGroup>().innerRadius(inner).outerRadius(outer);
          const ribbon = ribbonArrow<Chord, ChordGroup>().radius(inner - 2).padAngle(0.01);
          const label = (i: number) => flow.groups[i]!;
          return (
            <g transform={`translate(${width / 2},${height / 2})`}>
              {chords.map((c, i) => {
                const from = label(c.source.index);
                const to = label(c.target.index);
                const tip = {
                  title: from === to ? `Within ${from}` : `${from} → ${to}`,
                  rows: [
                    { label: "owed", value: weight(flow.matrix[c.source.index]![c.target.index]!), colour: colour(from) },
                    { label: "boons", value: formatValue(flow.counts[c.source.index]![c.target.index]!) },
                  ],
                };
                const mid = (c.target.startAngle + c.target.endAngle) / 2 - Math.PI / 2;
                return (
                  <g key={i} {...mark(tip, { x: width / 2 + Math.cos(mid) * inner * 0.6, y: height / 2 + Math.sin(mid) * inner * 0.6 })}>
                    <path d={(ribbon(c) as unknown as string) ?? ""} fill={colour(from)} fillOpacity={0.6} stroke="var(--chart-surface)" strokeWidth={1} />
                  </g>
                );
              })}
              {chords.groups.map((g) => {
                const name = label(g.index);
                const mid = (g.startAngle + g.endAngle) / 2;
                const owes = flow.matrix[g.index]!.reduce((n, v) => n + v, 0);
                const owed = flow.matrix.reduce((n, row) => n + row[g.index]!, 0);
                const tip = { title: name, rows: [{ label: "owes", value: weight(owes) }, { label: "is owed", value: weight(owed) }] };
                const right = mid < Math.PI;
                const lx = Math.sin(mid) * (outer + 6);
                const ly = -Math.cos(mid) * (outer + 6);
                return (
                  <g key={name} {...mark(tip, { x: width / 2 + Math.sin(mid) * outer, y: height / 2 - Math.cos(mid) * outer })}>
                    <path d={groupArc(g) ?? ""} fill={colour(name)} stroke="var(--chart-surface)" strokeWidth={2} />
                    {g.endAngle - g.startAngle > 0.12 && (
                      <text x={lx} y={ly} dy="0.32em" textAnchor={right ? "start" : "end"} style={{ fill: "var(--chart-ink-secondary)", fontSize: 11 }} pointerEvents="none">
                        {name}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        }}
      </ChartFrame>
    </div>
  );
}

// --- games ---------------------------------------------------------------------------------

function Games({ s }: { s: Statistics }) {
  const mark = useMarks();
  const dates = useDates();
  const games = useMemo(() => timeline(s.games), [s.games]);
  const [chosen, setChosen] = useState<string | null>(null);
  const picked: GameActivity | undefined = games.find((g) => g.game.id === chosen) ?? games.filter((g) => g.registered > 0).at(-1);
  const day = (g: GameActivity) => dates.date(g.game.starts_at);
  const table: ChartTable = {
    columns: [
      { key: "game", label: "Game" },
      ...KINDS.map((k) => ({ key: k.value, label: k.label, numeric: true })),
      { key: "registered", label: "Registered", numeric: true },
      { key: "settled", label: "Settled", numeric: true },
    ],
    rows: games.map((g) => ({ game: day(g), ...Object.fromEntries(KINDS.map((k) => [k.value, g.by_kind[k.value] ?? 0])), registered: g.registered, settled: g.settled })),
  };
  const most = Math.max(1, ...games.map((g) => g.registered));
  return (
    <div className="flex flex-col gap-3">
      <ChartFrame
        title="Boons at each game"
        description="Boons registered at each recent game, by kind: those staff registered at it, or entered from two hours before it started to twelve hours after it ended. Choose a game for what it did."
        height={220}
        table={table}
        state={games.length === 0 ? "empty" : "ready"}
        empty="No games on the schedule yet."
        legend={<Legend items={KIND_ITEMS} />}
      >
        {({ width, height }) => {
          const p = plotArea(width, height, { left: 36, top: 12 });
          const x = scaleBand(
            games.map((g) => g.game.id),
            [p.left, p.left + p.width],
          ).padding(0.25);
          const y = scaleLinear([0, most], [p.top + p.height, p.top]).nice();
          const w = Math.min(28, x.bandwidth());
          const every = Math.max(1, Math.ceil(games.length / Math.max(2, Math.floor(p.width / 96))));
          return (
            <>
              <AxisLeft scale={y} x={p.left} grid={p.width} count={4} />
              {games.map((g, i) => {
                const cx = (x(g.game.id) ?? 0) + x.bandwidth() / 2;
                const kinds = KINDS.filter((k) => (g.by_kind[k.value] ?? 0) > 0);
                let base = 0;
                const tip = {
                  title: day(g),
                  rows: [
                    ...kinds.map((k) => ({ label: k.label.toLowerCase(), value: formatValue(g.by_kind[k.value]!), colour: series(KIND_SLOT[k.value]) })),
                    { label: "registered", value: formatValue(g.registered) },
                    { label: "settled", value: formatValue(g.settled) },
                  ],
                };
                const handlers = mark(tip, { x: cx, y: y(g.registered) });
                return (
                  <g
                    key={g.game.id}
                    {...handlers}
                    onClick={() => {
                      setChosen(g.game.id);
                      handlers.onClick();
                    }}
                    aria-current={picked?.game.id === g.game.id ? "true" : undefined}
                  >
                    <rect x={x(g.game.id)} y={p.top} width={x.bandwidth()} height={p.height} fill={picked?.game.id === g.game.id ? "var(--chart-grid)" : "transparent"} />
                    {kinds.map((k, j) => {
                      const v = g.by_kind[k.value]!;
                      const y0 = y(base);
                      base += v;
                      const y1 = y(base);
                      const top = j === kinds.length - 1;
                      return <path key={k.value} d={columnPath(cx - w / 2, y1, w, Math.max(0, y0 - y1 - (top ? 0 : 2)), top)} fill={series(KIND_SLOT[k.value])} />;
                    })}
                    {i % every === 0 && (
                      <text x={cx} y={p.top + p.height + 16} textAnchor="middle" style={{ fill: "var(--chart-ink-secondary)", fontSize: 11 }} pointerEvents="none">
                        {day(g)}
                      </text>
                    )}
                  </g>
                );
              })}
            </>
          );
        }}
      </ChartFrame>
      {picked && (
        <section aria-label="The game chosen" className="rounded-lg border border-ash p-3 text-sm">
          <h4 className="text-gold">{day(picked)}</h4>
          <p className="text-mist">
            {picked.registered === 0
              ? "No boons registered at it."
              : `${picked.registered} ${picked.registered === 1 ? "boon" : "boons"} registered (weight ${weight(picked.registered_weight)}): ${KINDS.filter((k) => picked.by_kind[k.value])
                  .map((k) => `${picked.by_kind[k.value]} ${kindName(k.value).toLowerCase()}`)
                  .join(", ")}.`}{" "}
            {picked.settled > 0 && `${picked.settled} settled during it (weight ${weight(picked.settled_weight)}).`}
          </p>
          {picked.most_active.length > 0 && (
            <p className="mt-1">
              <span className="text-mist">Most active: </span>
              {picked.most_active.map((a) => `${a.who.name} (${a.boons})`).join(", ")}
            </p>
          )}
        </section>
      )}
    </div>
  );
}

// --- the page ------------------------------------------------------------------------------

/**
 * The statistics page, loaded on its own (it brings d3), for the troupe's running staff;
 * with `harpy`, as the Harpy reads it from their ledger page where the troupe allows it
 * (#749), who has left as the court knows it and nothing that opens the staff screens.
 */
export function BoonStatisticsPage({ troupeId, harpy = false }: { troupeId: string; harpy?: boolean }) {
  const [scope, setScope] = useState<Scope>("active");
  const found = useQuery({
    queryKey: ["boon-statistics", troupeId, scope],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-statistics", { params: { path: { troupe_id: troupeId }, query: { scope } } })),
    placeholderData: (previous) => previous,
  });
  // A clan keeps its colour in every chart: the troupe's clans by how many on its boons.
  const clanColours = useMemo(() => clanSlots((found.data?.nodes ?? []).filter((n) => n.who.character_id).map((n) => ({ clan: clanOf(n), count: 1 }))), [found.data]);
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const s = found.data;
  return (
    <div className="flex flex-col gap-4">
      <Card title="Boon statistics">
        <p className="mb-3 text-sm text-mist">
          How the boon ledger has moved over time, who owes whom, and how debt runs between clans and sects ({BOON_PAGE}). Weights are the troupe&apos;s, as on{" "}
          {harpy ? "the standings" : <Link to="../boon-standings">Boon standings</Link>}; every chart can be read as a table.
          {harpy && " Who has left is shown as the court knows it."}
        </p>
        <fieldset className="flex flex-wrap items-center gap-2 text-sm">
          <legend className="sr-only">Who is counted</legend>
          {SCOPES.map((o) => (
            <label key={o.value} className="flex items-center gap-1" title={o.meaning}>
              <input type="radio" name="boon-statistics-scope" checked={scope === o.value} onChange={() => setScope(o.value)} />
              {o.label}
            </label>
          ))}
          <span className="text-xs text-mist">{SCOPES.find((o) => o.value === scope)?.meaning}</span>
        </fieldset>
      </Card>
      <section aria-label="Over time" className="flex flex-col gap-2">
        <h2 className="text-lg text-gold">Over time</h2>
        <Trends s={s} />
      </section>
      <section aria-label="Who owes whom" className="flex flex-col gap-2">
        <h2 className="text-lg text-gold">Who owes whom</h2>
        <Network s={s} troupeId={troupeId} harpy={harpy} />
      </section>
      <section aria-label="Between clans and sects" className="flex flex-col gap-2">
        <h2 className="text-lg text-gold">Between clans and sects</h2>
        <FlowChart s={s} clanColours={clanColours} />
      </section>
      <section aria-label="Games" className="flex flex-col gap-2">
        <h2 className="text-lg text-gold">Games</h2>
        <Games s={s} />
      </section>
    </div>
  );
}
