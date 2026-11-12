import { describe, expect, it } from "vitest";
import type { ChartCycleOut, ChartEntryOut, HoldingOut } from "../../api/types";
import { conflictWeb, heatmap, holdingsTree, monthLabel, monthsBetween, perCycle } from "./influenceCharts";

let n = 0;
function entry(fields: Partial<ChartEntryOut>): ChartEntryOut {
  n += 1;
  return {
    id: `id-${n}`,
    short_id: `E${n}`,
    type: "elite",
    happened_at: "2026-07-11T19:30:00Z",
    character_id: "agnes",
    name: "Agnes",
    specialization: "News Media",
    action_key: "gossip_and_insider_trading",
    action: "2: Gossip and Insider Trading",
    level: 2,
    conflict: false,
    purpose: "",
    times: 1,
    blocks: 0,
    cycle_id: null,
    target_character_id: null,
    target_name: "",
    target_activity: "",
    ...fields,
  };
}

const conflict = (action_key: string, fields: Partial<ChartEntryOut> = {}) =>
  entry({ action_key, action: action_key, level: null, conflict: true, specialization: "", ...fields });

describe("the heatmap", () => {
  const entries = [
    entry({ happened_at: "2026-05-02T10:00:00Z", times: 2 }),
    entry({ happened_at: "2026-07-20T10:00:00Z" }),
    entry({ happened_at: "2026-07-21T10:00:00Z", specialization: "Finance", level: 5 }),
    entry({ type: "underworld", happened_at: "2026-07-01T10:00:00Z", specialization: "Transportation", level: 5 }),
    conflict("attack", { happened_at: "2026-07-02T10:00:00Z", specialization: "Finance", times: 3 }),
  ];

  it("counts actions by specialisation and month, every month in between, busiest row first", () => {
    const map = heatmap(entries, "elite", "actions");
    expect(map.months).toEqual(["2026-05", "2026-06", "2026-07"]);
    expect(map.rows.map((r) => [r.label, r.total])).toEqual([
      ["Finance", 4],
      ["News Media", 3],
    ]);
    const july = map.cells.find((c) => c.row === "elite|News Media" && c.month === "2026-07")!;
    expect(july.value).toBe(1);
    expect(map.max).toBe(4);
  });

  it("weighs by the general actions' levels, which leaves conflict actions out", () => {
    const map = heatmap(entries, "elite", "levels");
    expect(map.rows.map((r) => [r.label, r.total])).toEqual([
      ["News Media", 6],
      ["Finance", 5],
    ]);
    expect(map.cells.find((c) => c.row === "elite|Finance")!.entries).toHaveLength(1);
  });

  it("names each row's type when both are shown, and has nothing to show for no entries", () => {
    expect(heatmap(entries, "both", "actions").rows.map((r) => r.label)).toContain("Transportation (Underworld)");
    expect(heatmap([], "both", "actions")).toEqual({ rows: [], months: [], cells: [], max: 0 });
  });

  it("writes months short and steps across a year's end", () => {
    expect(monthLabel("2026-07")).toBe("Jul 26");
    expect(monthsBetween("2026-11", "2027-02")).toEqual(["2026-11", "2026-12", "2027-01", "2027-02"]);
  });
});

describe("the conflict web", () => {
  it("links who acted against or for whom, adding up repeats, and blocks to their activity", () => {
    const web = conflictWeb(
      [
        conflict("attack", { target_character_id: "bea", target_name: "Bea", times: 3, specialization: "Transportation" }),
        conflict("attack", { target_character_id: "bea", target_name: "Bea", short_id: "E99" }),
        conflict("boost", { character_id: "cal", name: "Cal", target_character_id: "bea", target_name: "Bea" }),
        conflict("block", { character_id: null, name: "The Prince's ghoul", target_activity: "Acquiring firearms" }),
      ],
      "both",
    );
    expect(web.links.map((l) => [l.source, l.target, l.kind, l.weight])).toEqual([
      ["c:agnes", "c:bea", "against", 4],
      ["c:cal", "c:bea", "support", 1],
      ["n:the prince's ghoul", "a:acquiring firearms", "block", 1],
    ]);
    expect(web.links[0]!.specializations).toEqual(["Transportation"]);
    expect(web.links[0]!.entries).toContain("E99");
    const bea = web.nodes.find((n) => n.key === "c:bea")!;
    expect([bea.in, bea.out]).toEqual([5, 0]);
    expect(web.nodes.find((n) => n.key === "a:acquiring firearms")!.kind).toBe("activity");
  });

  it("links nobody for a Defend of one's own, an unknown target or a discovery block, and counts the blocks", () => {
    const web = conflictWeb(
      [
        conflict("defend", { target_character_id: "agnes", target_name: "Agnes" }),
        conflict("attack"),
        conflict("discovery_block", { times: 2 }),
        conflict("attack", { target_name: "Someone", times: 1 }),
      ],
      "elite",
    );
    expect(web.links).toHaveLength(1);
    expect(web.nodes.find((n) => n.key === "c:agnes")!.discovery).toBe(2);
    expect(web.nodes.find((n) => n.key === "n:someone")!.kind).toBe("name");
  });

  it("shows only the type chosen", () => {
    const entries = [conflict("attack", { type: "underworld", target_character_id: "bea", target_name: "Bea" })];
    expect(conflictWeb(entries, "elite")).toEqual({ nodes: [], links: [] });
    expect(conflictWeb(entries, "underworld").links).toHaveLength(1);
  });
});

describe("who holds what", () => {
  const holding = (name: string, elite: number, underworld: number): HoldingOut => ({
    character_id: name.toLowerCase(),
    name,
    kind: "pc",
    elite,
    elite_specializations: elite ? ["News Media"] : [],
    underworld,
    underworld_specializations: [],
  });

  it("groups ratings by type, then character, largest first, leaving out none", () => {
    const tree = holdingsTree([holding("Agnes", 2, 0), holding("Bea", 4, 1)], "both");
    expect(tree.children.map((g) => [g.name, g.total, g.children.map((c) => c.name)])).toEqual([
      ["Elite", 6, ["Bea", "Agnes"]],
      ["Underworld", 1, ["Bea"]],
    ]);
    expect(tree.children[0]!.children[1]!.specializations).toEqual(["News Media"]);
    expect(holdingsTree([holding("Agnes", 2, 0)], "underworld").children).toEqual([]);
  });
});

describe("actions per cycle", () => {
  const cycles: ChartCycleOut[] = [
    { id: "aug", name: "August", opened_at: null, closes_at: "2026-08-31T00:00:00Z" },
    { id: "jul", name: "July", opened_at: null, closes_at: "2026-07-31T00:00:00Z" },
  ];

  it("counts each cycle's entries by type, a cycle's window taking those logged without one", () => {
    const found = perCycle(
      [
        entry({ cycle_id: "jul", times: 2 }),
        entry({ type: "underworld", happened_at: "2026-08-10T00:00:00Z" }),
        entry({ happened_at: "2026-07-05T00:00:00Z" }),
        entry({ happened_at: "2026-09-02T00:00:00Z", times: 4 }),
      ],
      cycles,
    );
    expect(found.rows.map((r) => [r.name, r.elite, r.underworld])).toEqual([
      ["July", 3, 0],
      ["August", 0, 1],
    ]);
    expect(found.outside).toBe(4);
  });
});
