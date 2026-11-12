import { useQuery } from "@tanstack/react-query";
import { hierarchy, tree, type HierarchyPointNode } from "d3-hierarchy";
import { linkHorizontal } from "d3-shape";
import { useMemo, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { SireLineNodeOut } from "../../api/types";
import { ChartFrame, clanKey, clanSlots, Legend, series, slotOf, useMarks, useZoom, ZoomControls, type Slot, type Tip } from "../../charts";
import { ErrorText } from "../../components/ui";
import { about, left, loneCount, ordinal, sireRows, sireTree, type SireTree } from "./sireLines";

// A row is a name and, under it, what the character is.
const ROW = 40;
const MARGIN = { left: 28, top: 20, right: 24, bottom: 20 };
const RADIUS = 6;
// From a node's centre to where its label starts.
const LABEL_GAP = RADIUS + 8;

/** About how wide a node's label is: its name at 13px, and what it is at 11px under it. */
function labelWidth(n: SireLineNodeOut, folded: number): number {
  const name = n.name.length + (folded ? ` +${folded}`.length : 0);
  return Math.ceil(Math.max(name * 7.4, about(n).join(" · ").length * 6.2));
}

/**
 * A troupe's sire lines (#707): a tree from each eldest known down to their childer,
 * drawn left to right so every name reads level. A tidy tree, not a radial one: the
 * names stay horizontal and a branch folds without moving the rest around the
 * circle. Depth is steps of descent from the eldest known, as generations in a
 * troupe often skip; each character's generation is under its name and in the table.
 *
 * Each character is coloured by clan, the troupe's clans keeping the same colours
 * as on every chart, and has its clan written under its name, so colour is never
 * all that tells it. A retired character is a ring, with how it left; a sire known
 * by name only, or outside the troupe, is a dashed ring.
 */
export function SireLines({ troupeId, open }: { troupeId: string; open: (node: SireLineNodeOut, staff: boolean) => void }) {
  const found = useQuery({
    queryKey: ["sire-lines", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/sire-lines", { params: { path: { troupe_id: troupeId } } })),
  });
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [lone, setLone] = useState(false);
  const zoom = useZoom({ min: 0.4, max: 4 });
  const nodes = useMemo(() => found.data?.nodes ?? [], [found.data]);
  const slots = useMemo(() => clanSlots((found.data?.clans ?? []).map((c) => ({ clan: c.clan, count: c.count }))), [found.data]);
  const shaped = useMemo(() => sireTree(nodes, { collapsed, lone }), [nodes, collapsed, lone]);

  if (found.error) return <ErrorText error={found.error} />;
  const alone = loneCount(nodes);
  const leaves = hierarchy(shaped, (d) => d.children).leaves().length;
  const height = Math.max(100, leaves * ROW + MARGIN.top + MARGIN.bottom);
  const order = (slot: Slot) => (slot === "other" ? 99 : slot);
  const clans = [...new Set(nodes.filter((n) => n.kind === "pc" || n.kind === "npc").map((n) => clanKey(n.clan)))].sort(
    (a, b) => order(slotOf(slots, a)) - order(slotOf(slots, b)) || a.localeCompare(b),
  );
  const toggle = (key: string) =>
    setCollapsed((was) => {
      const next = new Set(was);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <ChartFrame
      title="Sire lines"
      description={found.data?.staff ? "Who sired whom, from each eldest known down. Staff see every vampire in the troupe." : "Who sired whom among the characters on the Who's Who."}
      height={height}
      state={found.isPending ? "loading" : shaped.children.length === 0 ? "empty" : "ready"}
      empty={alone > 0 && !lone ? "No sires are known yet. A character's player gives its sire from the character's menu." : "No one to show yet."}
      table={{
        columns: [
          { key: "name", label: "Character" },
          { key: "sire", label: "Sire" },
          { key: "about", label: "Clan, generation and more" },
        ],
        rows: sireRows(nodes),
      }}
      svgRef={zoom.ref}
      legend={<Legend items={clans.map((c) => ({ key: c, label: c, colour: series(slotOf(slots, c)), mark: "dot" as const }))} />}
      controls={
        <div className="flex flex-wrap items-center gap-3">
          {alone > 0 && (
            <label className="flex items-center gap-1.5 text-sm text-mist">
              <input type="checkbox" checked={lone} onChange={(e) => setLone(e.target.checked)} />
              Show those with no known line ({alone})
            </label>
          )}
          <ZoomControls zoom={zoom} />
        </div>
      }
    >
      {({ width }) => (
        <g transform={zoom.transform.toString()}>
          <Drawing shaped={shaped} width={width} slots={slots} collapsed={collapsed} toggle={toggle} open={(n) => open(n, !!found.data?.staff)} />
        </g>
      )}
    </ChartFrame>
  );
}

type Point = HierarchyPointNode<SireTree>;

function Drawing({
  shaped,
  width,
  slots,
  collapsed,
  toggle,
  open,
}: {
  shaped: SireTree;
  width: number;
  slots: ReadonlyMap<string, Slot>;
  collapsed: ReadonlySet<string>;
  toggle: (key: string) => void;
  open: (node: SireLineNodeOut) => void;
}) {
  const mark = useMarks();
  const root = hierarchy(shaped, (d) => d.children);
  // Each column is as wide as its widest label, so a link starts after its sire's
  // label and never crosses it; it spreads to fill the width, and zoom and pan reach
  // past it.
  const widest = Math.max(0, ...root.descendants().map((d) => (d.data.node ? labelWidth(d.data.node, d.data.folded) : 0)));
  const fill = (width - MARGIN.left - MARGIN.right - widest) / Math.max(1, root.height - 1);
  const column = Math.max(widest + LABEL_GAP + 40, Math.min(fill, widest + 160));
  const laid = tree<SireTree>().nodeSize([ROW, column])(root);
  const all = laid.descendants().filter((d) => d.data.node);
  const top = Math.min(...all.map((d) => d.x));
  // The hidden root is depth 0: the eldest known stand in the first column.
  const at = (d: Point) => ({ x: MARGIN.left + (d.depth - 1) * column, y: MARGIN.top + d.x - top });
  const link = linkHorizontal<{ source: [number, number]; target: [number, number] }, [number, number]>();
  const from = (d: Point): [number, number] => {
    const { x, y } = at(d);
    return [x + LABEL_GAP + labelWidth(d.data.node!, d.data.folded) + 6, y];
  };
  const to = (d: Point): [number, number] => {
    const { x, y } = at(d);
    return [x - RADIUS - 2, y];
  };
  const byKey = new Map(all.map((d) => [d.data.node!.key, d]));

  return (
    <>
      <g fill="none" stroke="var(--chart-axis)" strokeWidth={1.5}>
        {all
          .filter((d) => d.parent?.data.node)
          .map((d) => (
            <path key={`link-${d.data.node!.key}`} d={link({ source: from(d.parent!), target: to(d) }) ?? ""} />
          ))}
      </g>
      {all.map((d) => {
        const n = d.data.node!;
        const { x, y } = at(d);
        const colour = series(slotOf(slots, clanKey(n.clan)));
        const outside = n.kind === "named" || n.kind === "elsewhere";
        const ring = n.retired || outside;
        const childer = d.children?.length ?? 0;
        const line = childer ? d.descendants().length - 1 : d.data.folded;
        const sire = n.sire_key ? byKey.get(n.sire_key)?.data.node?.name : undefined;
        const tip: Tip = {
          title: n.name,
          rows: [
            ...(n.clan ? [{ label: "clan", value: n.clan, colour: outside ? undefined : colour }] : []),
            ...(n.generation ? [{ label: "generation", value: ordinal(n.generation) }] : []),
            ...(sire ? [{ label: "sire", value: sire }] : []),
            ...(line ? [{ label: line === 1 ? "childe" : "of their line", value: String(line) }] : []),
            ...(n.retired ? [{ label: "left", value: left(n) }] : []),
            ...(n.kind === "named" ? [{ label: "by name only", value: "Known" }] : []),
            ...(n.kind === "elsewhere" ? [{ label: "the troupe", value: "Outside" }] : []),
          ],
        };
        const folded = collapsed.has(n.key);
        return (
          <g key={n.key}>
            <g {...mark(tip, { x, y })}>
              {/* A wider target than the mark, for a finger. */}
              <circle cx={x} cy={y} r={14} fill="transparent" />
              <circle
                cx={x}
                cy={y}
                r={RADIUS}
                fill={ring ? "var(--chart-surface)" : colour}
                stroke={outside ? "var(--chart-ink-secondary)" : ring ? colour : "var(--chart-surface)"}
                strokeWidth={2}
                strokeDasharray={outside ? "2 2" : undefined}
              />
            </g>
            <text x={x + LABEL_GAP} y={y - 3} fontSize={13} fill="var(--chart-ink)">
              {n.character_id && n.kind !== "elsewhere" ? (
                <a
                  href={`#c-${n.character_id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    open(n);
                  }}
                  className="hover:underline"
                >
                  {n.name}
                </a>
              ) : (
                <tspan fontStyle={n.kind === "named" ? "italic" : undefined}>{n.name}</tspan>
              )}
              {folded && d.data.folded > 0 && <tspan fill="var(--chart-ink-secondary)"> +{d.data.folded}</tspan>}
            </text>
            <text x={x + LABEL_GAP} y={y + 12} fontSize={11} fill="var(--chart-ink-secondary)">
              {about(n).join(" · ")}
            </text>
            {(childer > 0 || d.data.folded > 0) && (
              <g
                role="button"
                tabIndex={0}
                aria-expanded={!folded}
                aria-label={folded ? `Show ${n.name}'s childer` : `Fold ${n.name}'s childer`}
                className="cursor-pointer"
                onClick={() => toggle(n.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggle(n.key);
                  }
                }}
              >
                <rect x={x - 24} y={y - 9} width={16} height={18} rx={3} fill="var(--chart-surface)" stroke="var(--chart-axis)" />
                <text x={x - 16} y={y + 4} fontSize={12} textAnchor="middle" fill="var(--chart-ink-secondary)">
                  {folded ? "+" : "−"}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </>
  );
}
