import { useQuery } from "@tanstack/react-query";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { scaleLinear, scaleSqrt } from "d3-scale";
import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { levelName } from "../../bonds";
import { ChartFrame, clanKey, clanSlots, formatValue, Legend, series, slotOf, useMarks, useZoom, ZoomControls, type ChartTable, type LegendItem } from "../../charts";
import { ErrorText, Select } from "../../components/ui";
import { bondWeb, chains, DEFAULT_FILTERS, linkStatusText, mostThralls, standingText, webClans, type WebFilters, type WebLink, type WebNode } from "./bondWeb";

/*
 * The troupe's blood bonds as a web (#708), for the staff who run them: each
 * thrall linked to their regnant, heavier for a stronger bond, fading and ended
 * bonds faint. Loaded lazily, so d3 stays out of the rest of the troupe's pages.
 */

type Placed = WebNode & SimulationNodeDatum;

/** How each level of bond is drawn: heavier and brighter for a stronger bond. Neutral ink, so it never reads as a clan. */
const LINE: Record<number, { width: number; colour: string; opacity: number }> = {
  1: { width: 1.5, colour: "var(--chart-ink-secondary)", opacity: 0.6 },
  2: { width: 3, colour: "var(--chart-ink-secondary)", opacity: 0.9 },
  3: { width: 5, colour: "var(--chart-ink)", opacity: 1 },
};
const lineOf = (level: number) => LINE[Math.min(Math.max(level, 1), 3)]!;

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

function Tick({ checked, onChange, children }: { checked: boolean; onChange: (on: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex min-h-9 items-center gap-2 text-sm text-mist">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  );
}

const truncate = (text: string, length: number) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

export function BondWeb({ troupeId }: { troupeId: string }) {
  const [filters, setFilters] = useState<WebFilters>(DEFAULT_FILTERS);
  const set = (change: Partial<WebFilters>) => setFilters((f) => ({ ...f, ...change }));
  const found = useQuery({
    queryKey: ["bond-web", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/bond-web", { params: { path: { troupe_id: troupeId } } })),
  });
  const people = found.data?.people ?? [];
  const web = useMemo(() => bondWeb({ people, bonds: found.data?.bonds ?? [] }, filters), [found.data, people, filters]);
  // Clan colours from the troupe's own counts, as on its other charts; a web's nodes can sit side by side, so only three hues.
  const slots = useMemo(() => clanSlots(found.data?.clans ?? [], "allPairs"), [found.data]);
  const clans = webClans(people);
  return (
    <div className="flex flex-col gap-4">
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
        <Choice
          label="Bonds"
          value={filters.full ? "full" : "all"}
          onChange={(v) => set({ full: v === "full" })}
          options={[
            { value: "all", label: "Every level" },
            { value: "full", label: "Full bonds" },
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
        <Tick checked={filters.ended} onChange={(ended) => set({ ended })}>
          Ended and broken bonds
        </Tick>
      </div>
      {found.error && <ErrorText error={found.error} />}
      <Web troupeId={troupeId} web={web} slots={slots} loading={found.isPending} />
      {!found.isPending && <Findings web={web} />}
    </div>
  );
}

function Web({ troupeId, web, slots, loading }: { troupeId: string; web: ReturnType<typeof bondWeb>; slots: ReturnType<typeof clanSlots>; loading: boolean }) {
  const mark = useMarks();
  const zoom = useZoom();
  const [focus, setFocus] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  // Laid out once per web, in a unit square, then scaled to the card: a still picture, not a moving one.
  const placed = useMemo(() => {
    const nodes: Placed[] = web.nodes.map((n) => ({ ...n }));
    const links = web.links.map((l) => ({ source: l.thrall, target: l.regnant }));
    const simulation = forceSimulation(nodes)
      .force("charge", forceManyBody().strength(-80))
      .force("link", forceLink<Placed, (typeof links)[number]>(links).id((n) => n.key).distance(70))
      .force("collide", forceCollide(20))
      .force("x", forceX(0).strength(0.05))
      .force("y", forceY(0).strength(0.05))
      .stop();
    for (let i = 0; i < 300; i += 1) simulation.tick();
    return new Map(nodes.map((n) => [n.key, n]));
  }, [web]);
  const lit = focus ?? picked;
  const touches = (l: WebLink, key: string) => l.thrall === key || l.regnant === key;
  const near = new Set(lit ? web.links.filter((l) => touches(l, lit)).flatMap((l) => [l.thrall, l.regnant]) : []);
  const chosen = picked ? placed.get(picked) : undefined;

  const shownClans = [...new Set(web.nodes.map((n) => slotOf(slots, clanKey(n.clan))))];
  const legend: LegendItem[] = [
    ...[1, 2, 3].filter((level) => web.links.some((l) => l.open && Math.min(l.level, 3) === level)).map((level) => ({ key: `level-${level}`, label: levelName(level), colour: lineOf(level).colour, mark: "line" as const })),
    ...(web.links.some((l) => l.status !== "active") ? [{ key: "faint", label: "Fading, ended or broken", colour: "var(--chart-other)", mark: "line" as const }] : []),
    ...[...slots]
      .filter(([, slot]) => shownClans.includes(slot) && slot !== "other")
      .map(([clan, slot]) => ({ key: `clan-${clan}`, label: clan, colour: series(slot), mark: "dot" as const })),
    ...(shownClans.includes("other") ? [{ key: "clan-other", label: "Other clans", colour: series("other"), mark: "dot" as const }] : []),
  ];

  const table: ChartTable = {
    columns: [
      { key: "thrall", label: "Thrall" },
      { key: "regnant", label: "Regnant" },
      { key: "level", label: "Level" },
      { key: "status", label: "State" },
    ],
    rows: web.links.map((l) => ({
      thrall: placed.get(l.thrall)?.name ?? "",
      regnant: placed.get(l.regnant)?.name ?? "",
      level: levelName(l.level),
      status: linkStatusText(l),
    })),
  };
  const many = web.nodes.length > 30;

  return (
    <div className="flex flex-col gap-2">
      <ChartFrame
        title="The web of blood bonds"
        description="Each thrall with an arrow to their regnant, heavier for a stronger bond; fading, ended and broken bonds are faint. Each dot is coloured by clan and sized by how many thralls they hold. Select someone to light up their bonds."
        height={420}
        table={table}
        state={loading ? "loading" : web.links.length ? "ready" : "empty"}
        empty="No bonds to show with these filters."
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
          const size = scaleSqrt([0, Math.max(...all.map((n) => n.thralls), 1)], [6, 15]);
          return (
            <>
              <defs>
                {[1, 2, 3].map((level) => (
                  <marker key={level} id={`bond-arrow-${level}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                    <path d="M0,0L10,5L0,10z" fill={lineOf(level).colour} />
                  </marker>
                ))}
                <marker id="bond-arrow-faint" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                  <path d="M0,0L10,5L0,10z" fill="var(--chart-other)" />
                </marker>
              </defs>
              <rect x={0} y={0} width={width} height={height} fill="transparent" onClick={() => setPicked(null)} />
              {web.links.map((l) => {
                const s = placed.get(l.thrall)!;
                const t = placed.get(l.regnant)!;
                const a = at(s);
                const b = at(t);
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const len = Math.hypot(dx, dy) || 1;
                const r = size(t.thralls) + 4;
                const line = lineOf(l.level);
                const faint = l.status !== "active";
                const dim = lit !== null && !touches(l, lit);
                const tip = {
                  title: `${s.name} → ${t.name}`,
                  rows: [
                    { label: "level", value: levelName(l.level) },
                    { label: "state", value: linkStatusText(l) },
                    ...(l.fades_on ? [{ label: "fades by", value: l.fades_on }] : []),
                  ],
                };
                return (
                  <g key={l.id} {...mark(tip, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 })} data-bond={`${s.name} → ${t.name}`}>
                    <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={12} />
                    <line
                      x1={a.x}
                      y1={a.y}
                      x2={b.x - (dx / len) * r}
                      y2={b.y - (dy / len) * r}
                      data-level={l.level}
                      stroke={faint ? "var(--chart-other)" : line.colour}
                      strokeWidth={line.width}
                      strokeOpacity={dim ? 0.12 : faint ? 0.45 : line.opacity}
                      strokeDasharray={faint ? "4 4" : undefined}
                      strokeLinecap="round"
                      markerEnd={`url(#bond-arrow-${faint ? "faint" : Math.min(Math.max(l.level, 1), 3)})`}
                    />
                  </g>
                );
              })}
              {all.map((n) => {
                const p = at(n);
                const r = size(n.thralls);
                const dim = lit !== null && n.key !== lit && !near.has(n.key);
                const tip = {
                  title: n.name,
                  rows: [
                    { label: "clan", value: clanKey(n.clan) },
                    ...(n.titles.length ? [{ label: "holds", value: n.titles.join(", ") }] : []),
                    { label: "thralls bound to them", value: formatValue(n.thralls) },
                    { label: "bound to others", value: formatValue(n.boundTo) },
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
                      fill={series(slotOf(slots, clanKey(n.clan)))}
                      fillOpacity={n.standing === "active" ? 1 : 0.4}
                      stroke={n.key === picked ? "var(--chart-ink)" : "var(--chart-surface)"}
                      strokeWidth={2}
                      strokeDasharray={n.character_id === null ? "3 2" : undefined}
                    />
                    {(!many || n.thralls + n.boundTo >= 2 || n.key === lit) && (
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
      {chosen && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-mist" aria-live="polite">
          <span>
            <span className="text-parchment">{chosen.name}</span>: {chosen.thralls === 1 ? "1 thrall" : `${chosen.thralls} thralls`} bound to them, bound to{" "}
            {chosen.boundTo === 1 ? "1 regnant" : `${chosen.boundTo} regnants`}.
          </span>
          <Link to={`/troupes/${troupeId}/bonds?who=${encodeURIComponent(chosen.key)}`} className="text-gold underline">
            Open their bonds
          </Link>
        </p>
      )}
    </div>
  );
}

/** What the web says in words: who holds the most thralls, and where bonds run in a chain. */
function Findings({ web }: { web: ReturnType<typeof bondWeb> }) {
  const top = mostThralls(web);
  const chained = chains(web);
  if (!top.length && !chained.length) return null;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {top.length > 0 && (
        <section aria-label="Most thralls" className="rounded-lg border border-ash bg-dusk p-4">
          <h3 className="mb-2 text-base text-gold">Most thralls</h3>
          <ol className="flex flex-col gap-1 text-sm">
            {top.map((m) => (
              <li key={m.person.key} className="flex justify-between gap-3">
                <span>{m.person.name}</span>
                <span className="text-mist tabular-nums">
                  {m.thralls}
                  {m.full > 0 && ` (${m.full} full)`}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
      {chained.length > 0 && (
        <section aria-label="Chains of bonds" className="rounded-lg border border-ash bg-dusk p-4">
          <h3 className="mb-2 text-base text-gold">Chains of bonds</h3>
          <p className="mb-2 text-sm text-mist">Bound to someone, with thralls of their own.</p>
          <ul className="flex flex-col gap-1 text-sm">
            {chained.map((c) => (
              <li key={c.person.key}>
                <span className="text-mist">{c.thralls.join(", ")} → </span>
                <span className="text-parchment">{c.person.name}</span>
                <span className="text-mist"> → {c.regnants.join(", ")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
