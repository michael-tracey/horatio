import { useQuery } from "@tanstack/react-query";
import { scaleTime } from "d3-scale";
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { AxisBottom, ChartFrame, Legend, plotArea, series, useMarks, useZoom, ZoomControls, type ChartTable, type LegendItem, type Tip } from "../../charts";
import { ErrorText, Loading } from "../../components/ui";
import { extent, gameDate, kindOf, KINDS, placed, rangeOf, RANGES, rows as rowsOf, type ChronicleEvent, type Kind, type Placed, type Range } from "./chronicle";

const day = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const gameDay = (iso: string) => day.format(gameDate(iso));
const realDay = (iso: string) => day.format(new Date(iso));

/** When an event happened, in game where it has a date, and when Horatio recorded it. */
function dates(e: ChronicleEvent): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  if (e.on) out.push({ label: "in game", value: e.kind === "title" ? `${gameDay(e.on)} to ${e.ends_on ? gameDay(e.ends_on) : e.ongoing ? "now" : "?"}` : gameDay(e.on) });
  out.push({ label: "in Horatio", value: e.kind === "title" ? `${realDay(e.at)} to ${e.ends_at ? realDay(e.ends_at) : "now"}` : realDay(e.at) });
  return out;
}

/**
 * A troupe's chronicle (#711): its history in one timeline, one row per kind of
 * event or one per character, with titles as spans and the rest as moments.
 * In-game dates by default, where an event has one; those without are listed under
 * the chart. Zoom from centuries to nights. Loaded on its own, with the chart kit
 * (and d3), only when opened.
 */
export function ChronicleTab({ troupeId }: { troupeId: string }) {
  const chronicle = useQuery({
    queryKey: ["chronicle", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/chronicle", { params: { path: { troupe_id: troupeId } } })),
  });
  if (chronicle.isPending) return <Loading />;
  if (chronicle.error) return <ErrorText error={chronicle.error} />;
  return <Timeline events={chronicle.data.events} full={chronicle.data.full} />;
}

function Timeline({ events, full }: { events: ChronicleEvent[]; full: boolean }) {
  const [inGame, setInGame] = useState(true);
  const [by, setBy] = useState<"kind" | "character">("kind");
  const [range, setRange] = useState<Range>("all");
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [chosen, setChosen] = useState<ChronicleEvent | null>(null);
  const mark = useMarks();
  const zoom = useZoom({ min: 1, max: 200_000 });
  const ids = useId();
  const now = useMemo(() => new Date(), []);

  const { shown: all, undated } = useMemo(() => placed(events, inGame), [events, inGame]);
  const shown = useMemo(() => all.filter((p) => !hidden.has(p.event.kind)), [all, hidden]);
  // A title held still runs to now, or, in game, to the latest date shown if that is later.
  const openEnd = useMemo(() => all.reduce((max, p) => (p.from > max ? p.from : max), now), [all, now]);
  const rows = useMemo(() => rowsOf(shown, by, openEnd), [shown, by, openEnd]);
  const domain = useMemo(() => rangeOf(extent(all, openEnd), range), [all, openEnd, range]);

  const kindsHere = KINDS.filter((k) => all.some((p) => p.event.kind === k.kind));
  const legend: LegendItem[] = kindsHere.map((k) => ({ key: k.kind, label: k.label, colour: series(k.slot), mark: k.kind === "title" ? "rect" : "dot" }));
  const toggle = (key: string) =>
    setHidden((was) => {
      const next = new Set(was);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const table: ChartTable = {
    columns: [
      { key: "when", label: inGame ? "In game" : "In Horatio" },
      { key: "kind", label: "What" },
      { key: "label", label: "Event" },
      { key: "who", label: "Who" },
      ...(full ? [{ key: "detail", label: "Detail" }] : []),
    ],
    rows: shown.map(({ event: e, from, to, span }) => ({
      when: span ? `${day.format(from)} to ${to ? day.format(to) : "now"}` : day.format(from),
      kind: kindOf(e.kind).label,
      label: e.label,
      who: e.character_name,
      ...(full ? { detail: e.detail } : {}),
    })),
  };

  const LANE = 16;
  const GAP = 8;
  const height = Math.max(140, rows.reduce((sum, r) => sum + r.lanes * LANE + GAP, 0) + 44);

  const tipFor = ({ event: e }: Placed): Tip => ({
    title: `${e.label}: ${e.character_name}`,
    rows: [{ label: "what", value: kindOf(e.kind).label, colour: series(kindOf(e.kind).slot) }, ...dates(e), ...(full && e.detail ? [{ label: "detail", value: e.detail }] : [])],
  });

  const switches = (
    <div className="flex flex-wrap items-center gap-3 text-sm text-mist">
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={inGame} onChange={(e) => setInGame(e.target.checked)} />
        In-game dates
      </label>
      <label className="flex items-center gap-1">
        Rows
        <select className="rounded border border-ash bg-dusk px-1 py-0.5 text-parchment" value={by} onChange={(e) => setBy(e.target.value as "kind" | "character")}>
          <option value="kind">by kind</option>
          <option value="character">by character</option>
        </select>
      </label>
      <label className="flex items-center gap-1">
        Show
        <select
          className="rounded border border-ash bg-dusk px-1 py-0.5 text-parchment"
          value={range}
          onChange={(e) => {
            setRange(e.target.value as Range);
            zoom.reset();
          }}
        >
          {RANGES.map((r) => (
            <option key={r.range} value={r.range}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <ZoomControls zoom={zoom} />
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <ChartFrame
        title="The chronicle"
        description={
          (inGame ? "In-game dates, where the record has one." : "When Horatio recorded each event.") +
          " Titles are bars from when they were gained to when they were lost; everything else is a dot. Zoom with the buttons, a pinch, or Ctrl and the wheel; drag to move along."
        }
        height={height}
        table={table}
        svgRef={zoom.ref}
        state={all.length ? (shown.length ? "ready" : "empty") : "empty"}
        empty={all.length ? "Every kind is switched off: switch one back on in the key." : inGame ? "Nothing here has an in-game date yet." : "Nothing has happened here yet."}
        legend={<Legend items={legend} hidden={hidden} onToggle={toggle} />}
        controls={switches}
      >
        {({ width }) => {
          const p = plotArea(width, height, { left: Math.min(150, Math.max(84, width * 0.24)), top: 8, bottom: 28, right: 16 });
          const base = scaleTime(domain, [p.left, p.left + p.width]);
          const x = zoom.transform.rescaleX(base);
          let y = p.top;
          return (
            <>
              <defs>
                <clipPath id={`${ids}-plot`}>
                  <rect x={p.left} y={0} width={p.width} height={height} />
                </clipPath>
              </defs>
              {rows.map((row) => {
                const top = y;
                y = top + row.lanes * LANE + GAP;
                return (
                  <g key={row.key}>
                    <line x1={p.left} x2={p.left + p.width} y1={top + row.lanes * LANE + GAP / 2} y2={top + row.lanes * LANE + GAP / 2} stroke="var(--chart-grid)" />
                    <text x={p.left - 8} y={top + (row.lanes * LANE) / 2} dy="0.32em" textAnchor="end" style={{ fill: "var(--chart-ink)", fontSize: 12 }}>
                      {row.label.length > 22 ? `${row.label.slice(0, 21)}…` : row.label}
                    </text>
                    <g clipPath={`url(#${ids}-plot)`}>
                      {row.items.map(({ item, lane }) => {
                        const e = item.event;
                        const colour = series(kindOf(e.kind).slot);
                        const cy = top + lane * LANE + LANE / 2;
                        const x0 = x(item.from);
                        const props = mark(tipFor(item), { x: x0, y: cy - 6 });
                        const pick = {
                          ...props,
                          onClick: () => {
                            props.onClick();
                            setChosen(e);
                          },
                          onKeyDown: (k: KeyboardEvent<SVGElement>) => {
                            props.onKeyDown(k);
                            if (k.key === "Enter") setChosen(e);
                          },
                        };
                        if (item.span) {
                          const x1 = Math.max(x0 + 4, x(item.to ?? openEnd));
                          return (
                            <g key={e.key} {...pick}>
                              <rect x={x0} y={cy - 5} width={x1 - x0} height={10} rx={3} fill={colour} stroke="var(--chart-surface)" strokeWidth={2} />
                              {e.ongoing && <rect x={x1 - 3} y={cy - 5} width={3} height={10} fill="var(--chart-ink)" opacity={0.5} />}
                            </g>
                          );
                        }
                        return (
                          <g key={e.key} {...pick}>
                            {/* A larger, invisible target than the dot, for fingers. */}
                            <circle cx={x0} cy={cy} r={10} fill="transparent" />
                            <circle cx={x0} cy={cy} r={5} fill={colour} stroke="var(--chart-surface)" strokeWidth={2} />
                          </g>
                        );
                      })}
                    </g>
                  </g>
                );
              })}
              <AxisBottom scale={x} y={p.top + p.height} count={Math.max(2, Math.floor(p.width / 110))} />
            </>
          );
        }}
      </ChartFrame>
      {chosen && <Chosen event={chosen} full={full} onClose={() => setChosen(null)} />}
      {inGame && undated.length > 0 && <Undated events={undated} />}
    </div>
  );
}

/** The event last picked on the chart: everything the reader may know of it, and its record. */
function Chosen({ event: e, full, onClose }: { event: ChronicleEvent; full: boolean; onClose: () => void }) {
  return (
    <section aria-label="Chosen event" className="rounded-lg border border-ash bg-dusk p-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base text-gold">
          {e.label}: {e.character_name}
        </h3>
        <button type="button" className="text-sm text-mist underline hover:text-parchment" onClick={onClose}>
          Close
        </button>
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-mist">What</dt>
        <dd>{kindOf(e.kind as Kind).label}</dd>
        {e.clan && (
          <>
            <dt className="text-mist">Clan</dt>
            <dd>{e.clan}</dd>
          </>
        )}
        {dates(e).map((d) => (
          <div key={d.label} className="contents">
            <dt className="text-mist">{d.label[0]!.toUpperCase() + d.label.slice(1)}</dt>
            <dd>{d.value}</dd>
          </div>
        ))}
        {full && e.detail && (
          <>
            <dt className="text-mist">Detail</dt>
            <dd>{e.detail}</dd>
          </>
        )}
      </dl>
      {full && e.character_id && (
        <Link className="mt-2 inline-block text-gold underline" to={`/characters/${e.character_id}`}>
          Open {e.character_name}
        </Link>
      )}
    </section>
  );
}

/** What has no in-game date, so isn't on the in-game timeline: listed, so nothing goes missing. */
function Undated({ events }: { events: ChronicleEvent[] }) {
  return (
    <details className="rounded-lg border border-ash bg-dusk p-4 text-sm">
      <summary className="cursor-pointer text-mist">
        {events.length} {events.length === 1 ? "event has" : "events have"} no in-game date, so {events.length === 1 ? "it isn’t" : "they aren’t"} on the timeline above
      </summary>
      <p className="mt-2 text-xs text-mist">Joining the troupe, leaving it and retiring are only ever dated in Horatio. Untick In-game dates to see them.</p>
      <ul className="mt-2 flex flex-col gap-1">
        {events.map((e) => (
          <li key={e.key}>
            <span className="text-mist">{realDay(e.at)}</span> {e.label}: {e.character_name}
          </li>
        ))}
      </ul>
    </details>
  );
}
