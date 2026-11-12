import { createContext, useCallback, useContext, useMemo, useState, type KeyboardEvent, type PointerEvent, type ReactNode, type RefObject } from "react";

/** What a mark's tooltip says: a heading, then each value with what it is. */
export type Tip = { title?: string; rows: { label: string; value: string; colour?: string }[] };

/** Where a mark sits in the plot, for a tooltip shown by keyboard focus or a tap. */
export type Anchor = { x: number; y: number };

type Shown = { tip: Tip; x: number; y: number; pinned: boolean };

type Tooltips = {
  shown: Shown | null;
  show: (tip: Tip, at: Anchor, pinned?: boolean) => void;
  hide: (evenPinned?: boolean) => void;
  plot: RefObject<HTMLDivElement | null>;
};

const TooltipContext = createContext<Tooltips | null>(null);

/** Holds the one tooltip a chart shows at a time (ChartFrame puts it round the plot). */
export function TooltipProvider({ plot, children }: { plot: RefObject<HTMLDivElement | null>; children: ReactNode }) {
  const [shown, setShown] = useState<Shown | null>(null);
  const show = useCallback((tip: Tip, at: Anchor, pinned = false) => setShown({ tip, ...at, pinned }), []);
  const hide = useCallback((evenPinned = false) => setShown((s) => (s && s.pinned && !evenPinned ? s : null)), []);
  const value = useMemo(() => ({ shown, show, hide, plot }), [shown, show, hide, plot]);
  return <TooltipContext.Provider value={value}>{children}</TooltipContext.Provider>;
}

/** What a tip reads as, for a screen reader: "Minor: open 12". */
export function tipText(tip: Tip): string {
  const rows = tip.rows.map((r) => `${r.label} ${r.value}`).join(", ");
  return tip.title ? `${tip.title}: ${rows}` : rows;
}

/**
 * The props that make an SVG mark show its tooltip (#706): on hover, where the
 * pointer is; on keyboard focus, and on a tap (which keeps it until the next tap
 * or Escape), at `at`. Each mark can be reached with Tab and is read by its tip.
 * Tooltips add to what a chart shows, never gate it: every value is in the table too.
 *
 *     const mark = useMarks();
 *     <rect {...mark(tip, { x, y })} … />
 */
export function useMarks() {
  const tips = useContext(TooltipContext);
  return useCallback(
    (tip: Tip, at: Anchor) => {
      const near = (e: PointerEvent<SVGElement>): Anchor => {
        const box = tips?.plot.current?.getBoundingClientRect();
        return box ? { x: e.clientX - box.left, y: e.clientY - box.top } : at;
      };
      return {
        className: "chart-mark",
        tabIndex: 0,
        role: "img",
        "aria-label": tipText(tip),
        onPointerMove: (e: PointerEvent<SVGElement>) => {
          if (e.pointerType !== "touch" && !tips?.shown?.pinned) tips?.show(tip, near(e));
        },
        onPointerLeave: () => tips?.hide(),
        onClick: () => {
          const same = tips?.shown?.pinned && tipText(tips.shown.tip) === tipText(tip);
          if (same) tips?.hide(true);
          else tips?.show(tip, at, true);
        },
        onFocus: () => tips?.show(tip, at),
        onBlur: () => tips?.hide(true),
        onKeyDown: (e: KeyboardEvent<SVGElement>) => {
          if (e.key === "Escape") tips?.hide(true);
        },
      };
    },
    [tips],
  );
}

/** The tooltip itself, over the plot: values lead, what they are follows, keyed by a short line of the series colour. */
export function ChartTooltip({ width }: { width: number }) {
  const tips = useContext(TooltipContext);
  const shown = tips?.shown;
  if (!shown) return null;
  const left = Math.min(Math.max(shown.x, 96), Math.max(96, width - 96));
  const above = shown.y > 72;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute z-10 max-w-48 rounded-md border border-ash bg-night px-2.5 py-1.5 text-xs shadow-lg"
      style={{ left, top: shown.y, transform: `translate(-50%, ${above ? "calc(-100% - 10px)" : "14px"})` }}
    >
      {shown.tip.title && <p className="mb-0.5 text-mist">{shown.tip.title}</p>}
      <ul>
        {shown.tip.rows.map((r) => (
          <li key={r.label} className="flex items-center gap-1.5 whitespace-nowrap">
            {r.colour && <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: r.colour }} />}
            <strong className="font-semibold text-parchment tabular-nums">{r.value}</strong>
            <span className="text-mist">{r.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
