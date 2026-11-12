import { useQuery } from "@tanstack/react-query";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { scaleLinear, scaleSqrt } from "d3-scale";
import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { api, ApiError, unwrap } from "../../api/client";
import { levelName } from "../../bonds";
import { kindName } from "../../boons";
import { readableMinimum } from "../../boonStatistics";
import { ChartFrame, clanKey, clanSlots, diverging, formatValue, Legend, sequential, series, slotOf, useMarks, useZoom, ZoomControls, type ChartTable, type LegendItem } from "../../charts";
import { ErrorText, Select } from "../../components/ui";
import { linkStatusText, standingText } from "./bondWeb";
import { DEFAULT_FILTERS, LAYERS, net, obligationWeb, summary, webClans, type Filters, type Layer, type ObligationWeb as Web, type Person, type Sources, type Tie } from "./obligation";

/*
 * One web of obligation (#709), for the troupe's running staff: boons, blood bonds
 * and sire lines laid over one another on the same people, each a layer to switch
 * on and off. Each layer comes from its own chart's endpoint, so it shows only
 * where that chart would: boons while the troupe keeps a ledger, bonds to the staff
 * who run them while it tracks them. Loaded lazily, so d3 stays out of the rest of
 * the troupe's pages.
 */

type Placed = Person & SimulationNodeDatum;
type ColourBy = "clan" | "net" | "thralls";

/** How each layer's lines are drawn: told apart by dash as well as ink, so never by colour alone, and never in a clan's colour. */
const STYLE: Record<Layer, { colour: string; dash?: string; label: string }> = {
  boons: { colour: "var(--chart-ink)", label: "Boon owed (debtor → creditor)" },
  bonds: { colour: "var(--chart-ink-secondary)", dash: "7 4", label: "Blood bond (thrall → regnant)" },
  sires: { colour: "var(--chart-ink-secondary)", dash: "1 5", label: "Sire line (sire → childe)" },
};

/** A tie's stroke width: boons by weight, bonds by level, sire lines steady. */
function widthOf(t: Tie, heaviest: number): number {
  if (t.layer === "boons") return scaleSqrt([0, Math.max(heaviest, 1)], [1.25, 5])(t.weight ?? 0);
  if (t.layer === "bonds") return [1.5, 3, 4.5][Math.min(Math.max(t.level ?? 1, 1), 3) - 1]!;
  return 2;
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

function Tick({ checked, onChange, disabled, children }: { checked: boolean; onChange: (on: boolean) => void; disabled?: boolean; children: ReactNode }) {
  return (
    <label className={`flex min-h-9 items-center gap-2 text-sm ${disabled ? "text-mist/60" : "text-mist"}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  );
}

/** A layer's endpoint refuses (the troupe doesn't keep it, or the reader may not see it): the layer is simply missing. */
const refused = (error: unknown) => error instanceof ApiError && (error.status === 403 || error.status === 404);

const truncate = (text: string, length: number) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

export function ObligationWeb({ troupeId, boonsOn, bondsOn }: { troupeId: string; boonsOn: boolean; bondsOn: boolean }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [boonMinimum, setBoonMinimum] = useState<number | null>(null);
  const [colourBy, setColourBy] = useState<ColourBy>("clan");
  const set = (change: Partial<Filters>) => setFilters((f) => ({ ...f, ...change }));

  // The three charts' own endpoints, and their own caches: open one chart, then this, and nothing is fetched twice.
  const boons = useQuery({
    queryKey: ["boon-statistics", troupeId, filters.who],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-statistics", { params: { path: { troupe_id: troupeId }, query: { scope: filters.who } } })),
    enabled: boonsOn,
    retry: (count, error) => !refused(error) && count < 2,
  });
  const bonds = useQuery({
    queryKey: ["bond-web", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/bond-web", { params: { path: { troupe_id: troupeId } } })),
    enabled: bondsOn,
    retry: (count, error) => !refused(error) && count < 2,
  });
  const sires = useQuery({
    queryKey: ["sire-lines", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/sire-lines", { params: { path: { troupe_id: troupeId } } })),
    retry: (count, error) => !refused(error) && count < 2,
  });

  const have: Record<Layer, boolean> = { boons: !!boons.data, bonds: !!bonds.data, sires: !!sires.data?.staff };
  const sources = useMemo<Sources>(
    () => ({
      ...(boons.data ? { boons: boons.data } : {}),
      ...(bonds.data ? { bonds: bonds.data } : {}),
      ...(sires.data?.staff ? { sires: sires.data } : {}),
    }),
    [boons.data, bonds.data, sires.data],
  );
  // Start the boons where their own network does: light enough boons hidden to keep about 120 links.
  const minimum = boonMinimum ?? (boons.data ? readableMinimum(boons.data.links) : 0);
  const web = useMemo(() => obligationWeb(sources, { ...filters, boonMinimum: minimum }), [sources, filters, minimum]);
  // Clan colours from the troupe's own counts, as on its other charts; a web's dots can sit side by side, so only three hues.
  const slots = useMemo(() => clanSlots(bonds.data?.clans ?? sires.data?.clans ?? [], "allPairs"), [bonds.data, sires.data]);
  const clans = useMemo(() => webClans(sources), [sources]);
  const loading = (boonsOn && boons.isPending) || (bondsOn && bonds.isPending) || sires.isPending;
  const errors = [boons.error, bonds.error, sires.error].filter((e) => e && !refused(e));
  const missing = LAYERS.filter((l) => !have[l.value] && !loading);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        What ties the troupe&apos;s characters together, in one picture: boons owed, blood bonds and sire lines, each a layer of its own. Someone in more than one layer is one dot.
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2" role="group" aria-label="Layers">
        {LAYERS.map((l) => (
          <Tick
            key={l.value}
            checked={have[l.value] && filters.layers.has(l.value)}
            disabled={!have[l.value]}
            onChange={(on) => {
              const layers = new Set(filters.layers);
              if (on) layers.add(l.value);
              else layers.delete(l.value);
              set({ layers });
            }}
          >
            {l.label}
          </Tick>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Choice
          label="Who"
          value={filters.who}
          onChange={(who) => set({ who })}
          options={[
            { value: "active", label: "In play" },
            { value: "everyone", label: "Everyone" },
          ]}
        />
        <label className="flex items-center gap-2 text-sm text-mist">
          Clan
          <Select value={filters.clan ?? ""} onChange={(e) => set({ clan: e.target.value || null })} className="w-auto">
            <option value="">Every clan</option>
            {clans.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </label>
        <Tick checked={filters.titled} onChange={(titled) => set({ titled })}>
          Title holders
        </Tick>
        <label className="flex items-center gap-2 text-sm text-mist">
          Colour by
          <Select value={colourBy} onChange={(e) => setColourBy(e.target.value as ColourBy)} className="w-auto">
            <option value="clan">Clan</option>
            {have.boons && <option value="net">Net boon standing</option>}
            {have.bonds && <option value="thralls">Thralls held</option>}
          </Select>
        </label>
      </div>
      {(have.boons || have.bonds) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {have.boons && (
            <label className="flex items-center gap-2 text-sm text-mist">
              Boons weighing at least
              <input
                type="number"
                aria-label="Boons weighing at least"
                min={0}
                step={0.5}
                className="min-h-9 w-16 rounded-md border border-ash bg-night px-1 py-0.5 text-parchment"
                value={minimum}
                onChange={(e) => setBoonMinimum(Math.max(0, Number(e.target.value) || 0))}
              />
            </label>
          )}
          {have.bonds && (
            <Tick checked={filters.endedBonds} onChange={(endedBonds) => set({ endedBonds })}>
              Ended and broken bonds
            </Tick>
          )}
        </div>
      )}
      {errors.map((e, i) => (
        <ErrorText key={i} error={e} />
      ))}
      <Drawing web={web} slots={slots} colourBy={colourBy} loading={loading} />
      {missing.length > 0 && (
        <p className="text-sm text-mist">
          Not shown: {missing.map((l) => l.label.toLowerCase()).join(", ")}
          {", "}as the troupe doesn&apos;t keep {missing.length === 1 ? "it" : "them"}, or they&apos;re for other staff.
        </p>
      )}
    </div>
  );
}

function Drawing({ web, slots, colourBy, loading }: { web: Web; slots: ReturnType<typeof clanSlots>; colourBy: ColourBy; loading: boolean }) {
  const mark = useMarks();
  const zoom = useZoom();
  const navigate = useNavigate();
  const [focus, setFocus] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  // Laid out once per web, then scaled to the card: a still picture, not a moving one.
  const placed = useMemo(() => {
    const nodes: Placed[] = web.people.map((p) => ({ ...p }));
    const links = web.ties.map((t) => ({ source: t.from, target: t.to }));
    const simulation = forceSimulation(nodes)
      .force("charge", forceManyBody().strength(-90))
      .force("link", forceLink<Placed, (typeof links)[number]>(links).id((n) => n.key).distance(70))
      .force("collide", forceCollide(20))
      .force("x", forceX(0).strength(0.05))
      .force("y", forceY(0).strength(0.05))
      .stop();
    for (let i = 0; i < 300; i += 1) simulation.tick();
    return new Map(nodes.map((n) => [n.key, n]));
  }, [web]);

  const heaviestBoon = Math.max(0, ...web.ties.map((t) => t.weight ?? 0));
  const ties = (key: string) => web.ties.filter((t) => t.from === key || t.to === key).length;
  const mostTies = Math.max(1, ...web.people.map((p) => ties(p.key)));
  const widestNet = Math.max(1, ...web.people.map((p) => Math.abs(net(p))));
  const mostThralls = Math.max(1, ...web.people.map((p) => p.thralls));
  const fill = (p: Person) =>
    colourBy === "net" ? diverging(net(p) / widestNet) : colourBy === "thralls" ? sequential(p.thralls / mostThralls) : series(slotOf(slots, clanKey(p.clan)));

  const lit = focus ?? picked;
  const touches = (t: Tie, key: string) => t.from === key || t.to === key;
  const near = new Set(lit ? web.ties.filter((t) => touches(t, lit)).flatMap((t) => [t.from, t.to]) : []);
  const chosen = picked ? placed.get(picked) : undefined;
  const layersShown = LAYERS.filter((l) => web.ties.some((t) => t.layer === l.value));

  const shownClans = [...new Set(web.people.map((p) => slotOf(slots, clanKey(p.clan))))];
  const legend: LegendItem[] = [
    ...layersShown.map((l) => ({ key: `layer-${l.value}`, label: STYLE[l.value].label, colour: STYLE[l.value].colour, mark: "line" as const, dash: STYLE[l.value].dash })),
    ...(web.ties.some((t) => !t.open) ? [{ key: "faint", label: "Ended or broken bond", colour: "var(--chart-other)", mark: "line" as const, dash: STYLE.bonds.dash }] : []),
    ...(colourBy === "clan"
      ? [
          ...[...slots]
            .filter(([, slot]) => shownClans.includes(slot) && slot !== "other")
            .map(([clan, slot]) => ({ key: `clan-${clan}`, label: clan, colour: series(slot), mark: "dot" as const })),
          ...(shownClans.includes("other") ? [{ key: "clan-other", label: "Other clans", colour: series("other"), mark: "dot" as const }] : []),
        ]
      : colourBy === "net"
        ? [
            { key: "net-low", label: "Owes more", colour: diverging(-1), mark: "dot" as const },
            { key: "net-even", label: "Even", colour: diverging(0), mark: "dot" as const },
            { key: "net-high", label: "Owed more", colour: diverging(1), mark: "dot" as const },
          ]
        : [
            { key: "thralls-few", label: "No thralls", colour: sequential(0), mark: "dot" as const },
            { key: "thralls-most", label: `${mostThralls} ${mostThralls === 1 ? "thrall" : "thralls"}`, colour: sequential(1), mark: "dot" as const },
          ]),
  ];

  const tieText = (t: Tie) =>
    t.layer === "boons"
      ? `${t.count} ${t.count === 1 ? "boon" : "boons"}, weight ${formatValue(t.weight ?? 0)}`
      : t.layer === "bonds"
        ? `${levelName(t.level ?? 1)}${t.status && t.status !== "active" ? `, ${linkStatusText({ status: t.status }).toLowerCase()}` : ""}`
        : "Sire of";
  const table: ChartTable = {
    columns: [
      { key: "from", label: "From" },
      { key: "to", label: "To" },
      { key: "layer", label: "Tie" },
      { key: "what", label: "What" },
    ],
    rows: web.ties.map((t) => ({
      from: placed.get(t.from)?.name ?? "",
      to: placed.get(t.to)?.name ?? "",
      layer: LAYERS.find((l) => l.value === t.layer)!.label,
      what: tieText(t),
    })),
  };
  const many = web.people.length > 30;

  return (
    <div className="flex flex-col gap-2">
      <ChartFrame
        title="The web of obligation"
        description="Each dot a character, sized by how many ties it has. Solid arrows are boons owed, debtor to creditor, heavier for more weight; dashed arrows are blood bonds, thrall to regnant, heavier for a stronger bond; dotted arrows run from sire to childe. Select someone to light up their ties."
        height={460}
        table={table}
        state={loading ? "loading" : web.ties.length ? "ready" : "empty"}
        empty="No ties to show with these layers and filters."
        svgRef={zoom.ref}
        controls={<ZoomControls zoom={zoom} />}
        legend={<Legend items={legend} />}
      >
        {({ width, height }) => {
          const all = [...placed.values()];
          const xs = all.map((n) => n.x ?? 0);
          const ys = all.map((n) => n.y ?? 0);
          const pad = 32;
          const x = scaleLinear([Math.min(...xs), Math.max(...xs) || 1], [pad, width - pad]);
          const y = scaleLinear([Math.min(...ys), Math.max(...ys) || 1], [pad, height - pad]);
          const at = (n: Placed) => ({ x: zoom.transform.applyX(x(n.x ?? 0)), y: zoom.transform.applyY(y(n.y ?? 0)) });
          const size = scaleSqrt([0, mostTies], [6, 15]);
          return (
            <>
              <defs>
                {LAYERS.map((l) => (
                  <marker key={l.value} id={`tie-arrow-${l.value}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                    <path d="M0,0L10,5L0,10z" fill={STYLE[l.value].colour} />
                  </marker>
                ))}
                <marker id="tie-arrow-faint" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                  <path d="M0,0L10,5L0,10z" fill="var(--chart-other)" />
                </marker>
              </defs>
              <rect x={0} y={0} width={width} height={height} fill="transparent" onClick={() => setPicked(null)} />
              {web.ties.map((t) => {
                const s = placed.get(t.from)!;
                const e = placed.get(t.to)!;
                const a = at(s);
                const b = at(e);
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const len = Math.hypot(dx, dy) || 1;
                // Ties between the same pair (a boon, a bond, a sire line) bow apart, so each shows. The
                // side is measured from the pair, not the tie, so ties running opposite ways don't meet.
                const bow = t.layer === "boons" ? 0 : t.layer === "bonds" ? 22 : -22;
                const flip = t.from < t.to ? 1 : -1;
                const mx = (a.x + b.x) / 2 - (dy / len) * bow * flip;
                const my = (a.y + b.y) / 2 + (dx / len) * bow * flip;
                const r = size(ties(e.key)) + 4;
                const ex = b.x - ((b.x - mx) / (Math.hypot(b.x - mx, b.y - my) || 1)) * r;
                const ey = b.y - ((b.y - my) / (Math.hypot(b.x - mx, b.y - my) || 1)) * r;
                const style = STYLE[t.layer];
                const dim = lit !== null && !touches(t, lit);
                const tip = {
                  title: `${s.name} → ${e.name}`,
                  rows: [
                    { label: "tie", value: LAYERS.find((l) => l.value === t.layer)!.label },
                    ...(t.layer === "boons"
                      ? [
                          { label: "boons", value: formatValue(t.count ?? 0) },
                          { label: "weight", value: formatValue(t.weight ?? 0) },
                          ...(t.kind ? [{ label: "heaviest", value: kindName(t.kind) }] : []),
                        ]
                      : t.layer === "bonds"
                        ? [
                            { label: "level", value: levelName(t.level ?? 1) },
                            { label: "state", value: linkStatusText({ status: t.status ?? "active" }) },
                          ]
                        : []),
                  ],
                };
                const path = `M${a.x},${a.y}Q${mx},${my} ${ex},${ey}`;
                return (
                  <g key={t.key} {...mark(tip, { x: mx, y: my })} data-tie={t.layer} data-between={`${s.name} → ${e.name}`}>
                    <path d={path} fill="none" stroke="transparent" strokeWidth={12} />
                    <path
                      d={path}
                      fill="none"
                      stroke={t.open ? style.colour : "var(--chart-other)"}
                      strokeWidth={widthOf(t, heaviestBoon)}
                      strokeOpacity={dim ? 0.12 : t.open ? 0.9 : 0.45}
                      strokeDasharray={style.dash}
                      strokeLinecap="round"
                      markerEnd={`url(#tie-arrow-${t.open ? t.layer : "faint"})`}
                    />
                  </g>
                );
              })}
              {all.map((n) => {
                const p = at(n);
                const r = size(ties(n.key));
                const dim = lit !== null && n.key !== lit && !near.has(n.key);
                const tip = {
                  title: n.name,
                  rows: [
                    { label: "clan", value: clanKey(n.clan) },
                    ...(n.titles.length ? [{ label: "holds", value: n.titles.join(", ") }] : []),
                    ...summary(web, n),
                    ...(n.standing !== "active" ? [{ label: "now", value: standingText(n.standing) }] : []),
                    ...(n.character_id === null ? [{ label: "", value: "Name only" }] : []),
                  ],
                };
                const props = mark(tip, p);
                const pick = () => setPicked((k) => (k === n.key ? null : n.key));
                return (
                  <g
                    key={n.key}
                    {...props}
                    onPointerEnter={() => setFocus(n.key)}
                    onPointerLeave={() => {
                      props.onPointerLeave();
                      setFocus(null);
                    }}
                    onFocus={() => {
                      props.onFocus();
                      setFocus(n.key);
                    }}
                    onBlur={() => {
                      props.onBlur();
                      setFocus(null);
                    }}
                    onClick={() => {
                      props.onClick();
                      pick();
                    }}
                    onKeyDown={(e: KeyboardEvent<SVGElement>) => {
                      props.onKeyDown(e);
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        pick();
                      }
                    }}
                    opacity={dim ? 0.3 : 1}
                    data-person={n.name}
                  >
                    <circle cx={p.x} cy={p.y} r={r + 6} fill="transparent" />
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={r}
                      fill={fill(n)}
                      fillOpacity={n.standing === "active" ? 1 : 0.4}
                      stroke={n.key === picked ? "var(--chart-ink)" : "var(--chart-surface)"}
                      strokeWidth={2}
                      strokeDasharray={n.character_id === null ? "3 2" : undefined}
                    />
                    {(!many || ties(n.key) >= 3 || n.key === lit) && (
                      <text
                        x={p.x}
                        y={p.y + r + 12}
                        textAnchor="middle"
                        style={{ fill: "var(--chart-ink-secondary)", fontSize: 11, paintOrder: "stroke", stroke: "var(--chart-surface)", strokeWidth: 3, strokeLinejoin: "round" }}
                        pointerEvents="none"
                      >
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
      {chosen && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-mist" aria-live="polite">
          <span>
            <span className="text-parchment">{chosen.name}</span>:{" "}
            {summary(web, chosen)
              .map((r) => `${r.label} ${r.value}`)
              .join("; ")}
            .
          </span>
          {chosen.character_id && (
            <button type="button" className="text-gold underline" onClick={() => void navigate(`/characters/${chosen.character_id}`)}>
              Open their record
            </button>
          )}
        </p>
      )}
    </div>
  );
}
