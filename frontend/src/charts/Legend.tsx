/** One thing a legend names: its colour, and the mark it is drawn as (a bar's block, a line, a dot). */
export type LegendItem = { key: string; label: string; colour: string; mark?: "rect" | "line" | "dot" };

function Swatch({ colour, mark = "rect" }: Pick<LegendItem, "colour" | "mark">) {
  return (
    <svg width={14} height={10} aria-hidden="true" className="shrink-0">
      {mark === "line" && <line x1={1} x2={13} y1={5} y2={5} stroke={colour} strokeWidth={2} strokeLinecap="round" />}
      {mark === "dot" && <circle cx={7} cy={5} r={4} fill={colour} />}
      {mark === "rect" && <rect x={1} y={1} width={12} height={8} rx={2} fill={colour} />}
    </svg>
  );
}

/**
 * A chart's legend (#706), for two or more series: each colour with its name, in
 * the secondary ink (names never wear the series colour). With `onToggle`, each
 * entry is a button that hides or shows its series; hidden ones stay listed,
 * dimmed, so the others keep their colours.
 */
export function Legend({ items, hidden, onToggle }: { items: LegendItem[]; hidden?: ReadonlySet<string>; onToggle?: (key: string) => void }) {
  if (items.length < 2) return null;
  return (
    <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-mist">
      {items.map((item) => {
        const off = hidden?.has(item.key) ?? false;
        const body = (
          <>
            <Swatch colour={item.colour} mark={item.mark} />
            <span className={off ? "line-through opacity-60" : undefined}>{item.label}</span>
          </>
        );
        return (
          <li key={item.key}>
            {onToggle ? (
              <button type="button" aria-pressed={!off} onClick={() => onToggle(item.key)} className="inline-flex min-h-6 items-center gap-1.5 hover:text-parchment">
                {body}
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5">{body}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
