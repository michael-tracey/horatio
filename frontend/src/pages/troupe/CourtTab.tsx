import { useQuery } from "@tanstack/react-query";
import { scaleLinear, scaleTime } from "d3-scale";
import { area, curveStepAfter } from "d3-shape";
import { useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { AxisBottom, AxisLeft, ChartFrame, clanKey, clanSlots, Legend, plotArea, series, slotOf, useMarks, type ChartTable, type LegendItem, type Tip } from "../../charts";
import { Button, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { courtRows, dated, span, statusExtent, type CourtHolding, type Dates } from "./court";

type CourtHistory = components["schemas"]["CourtHistoryOut"];
type StatusLine = components["schemas"]["StatusLineOut"];

const day = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const when = (iso: string | null | undefined): string => (iso ? day.format(new Date(iso)) : "now");

const BEGAN: Record<string, string> = { given: "given by staff", chosen: "chosen by the player", unknown: "how, unknown" };
const ENDED: Record<string, string> = {
  taken: "taken by staff",
  given_up: "given up",
  retired: "given up on retiring",
  left: "left the troupe",
  removed: "title removed from the troupe",
  deleted: "character deleted",
  unknown: "how, unknown",
};

/**
 * The court over time (#712): one row per title, in court order and grouped by
 * sect, with a bar for each holding, coloured by the holder's clan. Under it, for
 * staff, each home character's status over time. Loaded on its own, with the
 * chart kit (and d3), only when opened.
 */
export function CourtTab({ troupeId }: { troupeId: string }) {
  const court = useQuery({
    queryKey: ["court-history", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/court-history", { params: { path: { troupe_id: troupeId } } })),
  });
  if (court.isPending) return <Loading />;
  if (court.error) return <ErrorText error={court.error} />;
  const data = court.data;
  return (
    <div className="flex flex-col gap-4">
      <TitlesChart data={data} />
      {data.full && data.status && <StatusChart lines={data.status} />}
      {data.full && <InGameDates troupeId={troupeId} holdings={data.holdings} />}
    </div>
  );
}

function TitlesChart({ data }: { data: CourtHistory }) {
  const [inGame, setInGame] = useState(false);
  const mark = useMarks();
  const navigate = useNavigate();
  const slots = useMemo(() => clanSlots(data.clans.map((c) => ({ clan: c.clan, count: c.count }))), [data.clans]);
  const shown: Dates[] = useMemo(() => dated(data.holdings as CourtHolding[], inGame), [data.holdings, inGame]);
  const rows = useMemo(() => courtRows(data.titles, shown), [data.titles, shown]);
  const undated = data.holdings.length - shown.length;

  const clansShown = [...new Set(shown.map((d) => clanKey(d.holding.clan)))];
  const legend: LegendItem[] = clansShown.map((clan) => ({ key: clan, label: clan, colour: series(slotOf(slots, clan)) }));
  const table: ChartTable = {
    columns: [
      { key: "title", label: "Title" },
      { key: "holder", label: "Holder" },
      { key: "clan", label: "Clan" },
      { key: "from", label: "From" },
      { key: "to", label: "To" },
      ...(data.full ? [{ key: "how", label: "How it ended" }] : []),
    ],
    rows: shown.map(({ holding: h, from, to }) => ({
      title: h.title,
      holder: h.character_name,
      clan: clanKey(h.clan),
      from: day.format(from),
      to: to ? day.format(to) : "holds it still",
      ...(data.full ? { how: h.ended_how ? (ENDED[h.ended_how] ?? h.ended_how) : "" } : {}),
    })),
  };
  const LANE = 18;
  const GAP = 6;
  const height = Math.max(120, rows.reduce((sum, r) => sum + r.lanes * LANE + GAP + (r.sectStart ? 18 : 0), 0) + 40);

  const tipFor = ({ holding: h, from, to }: Dates): Tip => ({
    title: `${h.title}: ${h.character_name}`,
    rows: [
      { label: "from", value: day.format(from) },
      { label: "to", value: to ? day.format(to) : "holds it still" },
      ...(!inGame && h.began_in_game ? [{ label: "in game", value: `${when(h.began_in_game)} to ${h.ended_at ? when(h.ended_in_game) : "now"}` }] : []),
      ...(h.began_how ? [{ label: "began", value: BEGAN[h.began_how] ?? h.began_how }] : []),
      ...(h.ended_how ? [{ label: "ended", value: ENDED[h.ended_how] ?? h.ended_how }] : []),
      { label: "clan", value: clanKey(h.clan), colour: series(slotOf(slots, clanKey(h.clan))) },
    ],
  });

  const open = (h: CourtHolding) => {
    if (data.full && h.character_id) void navigate(`/characters/${h.character_id}`);
  };

  return (
    <ChartFrame
      title="Who held each title"
      description={
        (inGame ? "In-game dates, where staff gave them." : "When each holding began and ended in Horatio.") +
        (data.full ? " Double-click a bar, or press Enter on it, to open the character." : "")
      }
      height={height}
      table={table}
      state={shown.length ? "ready" : "empty"}
      empty={inGame ? "No holding has in-game dates yet." : "No one has held a title here yet."}
      legend={<Legend items={legend} />}
      controls={
        <label className="flex items-center gap-1 text-sm text-mist">
          <input type="checkbox" checked={inGame} onChange={(e) => setInGame(e.target.checked)} />
          In-game dates
          {inGame && undated > 0 && <span className="text-xs">({undated} without)</span>}
        </label>
      }
    >
      {({ width }) => {
        const p = plotArea(width, height, { left: Math.min(160, Math.max(96, width * 0.28)), top: 8, bottom: 28, right: 16 });
        const now = new Date();
        const first = shown.reduce((min, d) => (d.from < min ? d.from : min), now);
        const last = shown.reduce((max, d) => (d.to && d.to > max ? d.to : max), inGame ? first : now);
        const x = scaleTime(span(first, last), [p.left, p.left + p.width]);
        let y = p.top;
        return (
          <>
            {rows.map((row) => {
              const top = y + (row.sectStart ? 18 : 0);
              y = top + row.lanes * LANE + GAP;
              return (
                <g key={row.name}>
                  {row.sectStart && (
                    <text x={0} y={top - 6} style={{ fill: "var(--chart-ink-secondary)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {row.sectStart}
                    </text>
                  )}
                  <line x1={p.left} x2={p.left + p.width} y1={top + row.lanes * LANE + GAP / 2} y2={top + row.lanes * LANE + GAP / 2} stroke="var(--chart-grid)" />
                  <text x={p.left - 8} y={top + (row.lanes * LANE) / 2} dy="0.32em" textAnchor="end" style={{ fill: "var(--chart-ink)", fontSize: 12 }}>
                    {row.name}
                  </text>
                  {row.items.map(({ dates, lane }) => {
                    const x0 = x(dates.from);
                    const x1 = Math.max(x0 + 3, x(dates.to ?? (inGame ? last : now)));
                    const by = top + lane * LANE + 2;
                    const h = dates.holding;
                    const tip = tipFor(dates);
                    const props = mark(tip, { x: (x0 + x1) / 2, y: by });
                    return (
                      <g
                        key={h.id}
                        {...props}
                        onDoubleClick={() => open(h)}
                        onKeyDown={(e: KeyboardEvent<SVGElement>) => {
                          props.onKeyDown(e);
                          if (e.key === "Enter") open(h);
                        }}
                      >
                        <rect x={x0} y={by} width={x1 - x0} height={LANE - 4} rx={3} fill={series(slotOf(slots, clanKey(h.clan)))} stroke="var(--chart-surface)" strokeWidth={1} />
                        {!dates.to && <rect x={x1 - 3} y={by} width={3} height={LANE - 4} fill="var(--chart-ink)" opacity={0.5} />}
                      </g>
                    );
                  })}
                </g>
              );
            })}
            <AxisBottom scale={x} y={p.top + p.height} count={Math.max(2, Math.floor(p.width / 110))} />
          </>
        );
      }}
    </ChartFrame>
  );
}

/** Each home character's fleeting and negative status over time, one small chart each, on one scale. */
function StatusChart({ lines }: { lines: StatusLine[] }) {
  const mark = useMarks();
  const legend: LegendItem[] = [
    { key: "fleeting", label: "Fleeting", colour: series(1) },
    { key: "negative", label: "Negative", colour: series(2) },
  ];
  const { start, end, most } = statusExtent(lines);
  const table: ChartTable = {
    columns: [
      { key: "name", label: "Character" },
      { key: "fleeting", label: "Fleeting now", numeric: true },
      { key: "negative", label: "Negative now", numeric: true },
      { key: "gained", label: "Gained", numeric: true },
      { key: "lost", label: "Spent or lost", numeric: true },
    ],
    rows: lines.map((l) => {
      const now = l.points[l.points.length - 1];
      return { name: l.name, fleeting: now?.fleeting ?? 0, negative: now?.negative ?? 0, gained: l.gained, lost: l.lost };
    }),
  };
  const CELL = 96;
  return (
    <ChartFrame
      title="Status over time"
      description="How much fleeting and negative status each home character held, from the troupe’s log: one small chart each, on the same scale."
      height={Math.max(CELL, Math.ceil(lines.length / 2) * (CELL + 28))}
      table={table}
      state={lines.length ? "ready" : "empty"}
      empty="No home character has gained or held status yet."
      legend={<Legend items={legend} />}
    >
      {({ width }) => {
        const columns = width >= 900 ? 3 : width >= 520 ? 2 : 1;
        const cellW = width / columns;
        return lines.map((line, i) => {
          const cx = (i % columns) * cellW;
          const cy = Math.floor(i / columns) * (CELL + 28);
          const p = plotArea(cellW, CELL, { left: 28, top: 18, right: 12, bottom: 20 });
          const x = scaleTime([start, end], [cx + p.left, cx + p.left + p.width]);
          const y = scaleLinear([0, most], [cy + p.top + p.height, cy + p.top]).nice();
          const points = [...line.points.map((pt) => ({ at: new Date(pt.at), fleeting: pt.fleeting, negative: pt.negative })), { at: end, fleeting: 0, negative: 0 }];
          const last = line.points[line.points.length - 1];
          points[points.length - 1] = { at: end, fleeting: last?.fleeting ?? 0, negative: last?.negative ?? 0 };
          const fleeting = area<(typeof points)[number]>()
            .x((d) => x(d.at))
            .y0(() => y(0))
            .y1((d) => y(d.fleeting))
            .curve(curveStepAfter);
          const negative = area<(typeof points)[number]>()
            .x((d) => x(d.at))
            .y0((d) => y(d.fleeting))
            .y1((d) => y(d.fleeting + d.negative))
            .curve(curveStepAfter);
          const tip: Tip = {
            title: line.name,
            rows: [
              { label: "fleeting now", value: String(last?.fleeting ?? 0), colour: series(1) },
              { label: "negative now", value: String(last?.negative ?? 0), colour: series(2) },
              { label: "gained", value: String(line.gained) },
              { label: "spent or lost", value: String(line.lost) },
            ],
          };
          return (
            <g key={line.character_id} {...mark(tip, { x: cx + cellW / 2, y: cy + p.top })}>
              <text x={cx + p.left} y={cy + 12} style={{ fill: "var(--chart-ink)", fontSize: 12 }}>
                {line.name}
              </text>
              <rect x={cx + p.left} y={cy + p.top} width={p.width} height={p.height} fill="transparent" />
              <AxisLeft scale={y} x={cx + p.left} grid={p.width} count={2} />
              <path d={fleeting(points) ?? ""} fill={series(1)} />
              <path d={negative(points) ?? ""} fill={series(2)} />
            </g>
          );
        });
      }}
    </ChartFrame>
  );
}

/** Staff give a holding its in-game dates: the real dates are always kept beside them. */
function InGameDates({ troupeId, holdings }: { troupeId: string; holdings: CourtHistory["holdings"] }) {
  return (
    <details className="rounded-lg border border-ash bg-dusk p-4 text-sm">
      <summary className="cursor-pointer text-gold">In-game dates</summary>
      <p className="mt-2 text-mist">Give a holding the in-game dates it began and ended, to see the court in the chronicle’s own time.</p>
      <ul className="mt-2 divide-y divide-ash/60">
        {[...holdings].reverse().map((h) => (
          <HoldingDates key={h.id} troupeId={troupeId} holding={h} />
        ))}
      </ul>
    </details>
  );
}

function HoldingDates({ troupeId, holding }: { troupeId: string; holding: CourtHistory["holdings"][number] }) {
  const [began, setBegan] = useState(holding.began_in_game ?? "");
  const [ended, setEnded] = useState(holding.ended_in_game ?? "");
  const save = useAction(() =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/court-history/{holding_id}/in-game", {
        params: { path: { troupe_id: troupeId, holding_id: holding.id } },
        body: { began_in_game: began || null, ended_in_game: ended || null },
      }),
    ),
  );
  const changed = began !== (holding.began_in_game ?? "") || ended !== (holding.ended_in_game ?? "");
  const label = `${holding.title}: ${holding.character_name}`;
  return (
    <li className="flex flex-wrap items-end gap-3 py-2">
      <div className="min-w-48 grow">
        <p>{label}</p>
        <p className="text-xs text-mist">
          {when(holding.began_at)} to {holding.ended_at ? when(holding.ended_at) : "now"}
        </p>
      </div>
      <label className="flex flex-col text-xs text-mist">
        Began in game
        <Input type="date" value={began} onChange={(e) => setBegan(e.target.value)} aria-label={`${label}: began in game`} />
      </label>
      {holding.ended_at && (
        <label className="flex flex-col text-xs text-mist">
          Ended in game
          <Input type="date" value={ended} onChange={(e) => setEnded(e.target.value)} aria-label={`${label}: ended in game`} />
        </label>
      )}
      <Button disabled={!changed || save.isPending} onClick={() => save.mutate(undefined)}>
        Save
      </Button>
      <ErrorText error={save.error} />
    </li>
  );
}
