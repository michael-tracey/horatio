import { useId, useRef, useState, type ReactNode, type Ref } from "react";
import { EmptyState } from "../components/EmptyState";
import { Loader } from "../components/ui";
import { useWidth } from "./hooks";
import { ChartTooltip, TooltipProvider } from "./Tooltip";
import "./charts.css";

/** A chart's data as a table: its twin for screen readers, and for anyone who asks. */
export type ChartTable = {
  columns: { key: string; label: string; numeric?: boolean }[];
  rows: Record<string, string | number>[];
};

/** The space inside a chart's margins, where the marks go. */
export type Plot = { width: number; height: number; left: number; top: number; right: number; bottom: number };

/** The plot inside a chart of `width` × `height`, with room for its axes. */
export function plotArea(width: number, height: number, margin: Partial<Pick<Plot, "left" | "top" | "right" | "bottom">> = {}): Plot {
  const { left = 40, top = 8, right = 12, bottom = 28 } = margin;
  return { left, top, right, bottom, width: Math.max(0, width - left - right), height: Math.max(0, height - top - bottom) };
}

export function TableView({ table, caption, className }: { table: ChartTable; caption: string; className?: string }) {
  return (
    <div className={className}>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-ash text-xs text-mist">
            {table.columns.map((c) => (
              <th key={c.key} scope="col" className={c.numeric ? "py-1 pr-2 text-right font-normal" : "py-1 pr-2 font-normal"}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className="border-b border-ash/60 last:border-0">
              {table.columns.map((c) => (
                <td key={c.key} className={c.numeric ? "py-1 pr-2 text-right tabular-nums" : "py-1 pr-2"}>
                  {row[c.key] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The card every chart sits in (#706): its title and what it shows, its legend,
 * the plot, and a button to see the same data as a table. The table is always
 * there for screen readers. The plot fills the card's width and is `height`
 * tall, axes included, so the card never scrolls inside itself.
 *
 * While loading for the first time it shows the loader; with nothing to show,
 * `empty`, keeping its `controls`, so a filter that empties the chart can be undone.
 * While `refreshing`, the last drawing stays, faded, rather than
 * jumping. `children` draws the marks for the measured size.
 */
export function ChartFrame({
  title,
  description,
  height,
  table,
  state = "ready",
  empty = "Nothing to show yet.",
  refreshing = false,
  legend,
  controls,
  svgRef,
  children,
}: {
  title: string;
  description: string;
  height: number;
  table: ChartTable;
  state?: "ready" | "loading" | "empty";
  empty?: ReactNode;
  refreshing?: boolean;
  legend?: ReactNode;
  controls?: ReactNode;
  svgRef?: Ref<SVGSVGElement>;
  children: (size: { width: number; height: number }) => ReactNode;
}) {
  const id = useId();
  const [asTable, setAsTable] = useState(false);
  const { ref, width } = useWidth<HTMLDivElement>();
  const plot = useRef<HTMLDivElement>(null);
  const ready = state === "ready";
  return (
    <figure className="chart flex flex-col gap-2 rounded-lg border border-ash bg-dusk p-4 sm:p-5" aria-labelledby={`${id}-title`}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={`${id}-title`} className="text-base text-gold">
            {title}
          </h3>
          <p id={`${id}-desc`} className="text-sm text-mist">
            {description}
          </p>
        </div>
        {(ready || state === "empty") && (
          <div className="flex flex-wrap items-center gap-2">
            {(!asTable || !ready) && controls}
            {ready && (
              <button type="button" aria-pressed={asTable} onClick={() => setAsTable((t) => !t)} className="min-h-8 text-sm text-mist underline hover:text-parchment">
                {asTable ? "Show as chart" : "Show as table"}
              </button>
            )}
          </div>
        )}
      </header>
      {ready && !asTable && legend}
      <div ref={ref} className="min-w-0">
        {state === "loading" && <Loader compact label="Loading the chart…" />}
        {state === "empty" && <EmptyState title={empty} />}
        {ready && asTable && <TableView table={table} caption={title} className="overflow-x-auto" />}
        {ready && !asTable && (
          <TooltipProvider plot={plot}>
            <div ref={plot} className="chart-plot relative" style={{ height, opacity: refreshing ? 0.55 : 1 }}>
              {width > 0 && (
                <svg ref={svgRef} width={width} height={height} role="group" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`} className="block overflow-visible">
                  {children({ width, height })}
                </svg>
              )}
              <ChartTooltip width={width} />
            </div>
            <TableView table={table} caption={title} className="sr-only" />
          </TooltipProvider>
        )}
      </div>
    </figure>
  );
}
