import { describe, expect, it } from "vitest";
import { flowPairs, folded, monthLabel, monthsBetween, network, readableMinimum, timeline, trend, type MonthLine, type StatLink, type StatNode, type Weights } from "./boonStatistics";

const WEIGHTS: Weights = { trivial: 0.5, minor: 1, major: 3, blood: 5, life: 10 };
const ALL = new Set(["trivial", "minor", "major", "blood", "life"] as const);

function month(m: string, kind: MonthLine["kind"], values: Partial<MonthLine> = {}): MonthLine {
  return { month: m, kind, registered: 0, registered_weight: 0, settled: 0, settled_weight: 0, open: 0, open_weight: 0, ...values };
}

function node(key: string, clan: string | null, extra: Partial<StatNode["who"]> = {}): StatNode {
  return {
    who: { key, name: key, character_id: key, standing: "active", clan, age: "Neonate", sect: "Camarilla", titles: [], ...extra },
    owes: 0,
    owed: 0,
    net: 0,
    owes_count: 0,
    owed_count: 0,
  };
}

function link(debtor: string, creditor: string, kinds: Record<string, number>): StatLink {
  const weight = Object.entries(kinds).reduce((n, [k, c]) => n + c * WEIGHTS[k as keyof Weights], 0);
  return { debtor, creditor, kinds, count: Object.values(kinds).reduce((a, b) => a + b, 0), weight };
}

describe("months", () => {
  it("runs from the first to the last across a new year", () => {
    expect(monthsBetween("2025-11", "2026-02")).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(monthLabel("2026-10")).toBe("Oct 2026");
  });
});

describe("trend", () => {
  it("counts each kind each month, filling the months between", () => {
    const found = trend([month("2026-08", "minor", { registered: 2 }), month("2026-10", "major", { registered: 1, registered_weight: 3 })], "registered", false);

    expect(found.periods.map((p) => p.label)).toEqual(["Aug 2026", "Sep 2026", "Oct 2026"]);
    expect(found.byKind.minor).toEqual([2, 0, 0]);
    expect(found.byKind.major).toEqual([0, 0, 1]);
    expect(found.totals).toEqual([2, 0, 1]);
  });

  it("goes by year past five years, summing registered but keeping a year's last open", () => {
    const lines = [
      month("1991-12", "minor", { registered: 1, open: 1 }),
      month("2026-01", "minor", { registered: 2, open: 3 }),
      month("2026-11", "minor", { registered: 1, open: 2 }),
    ];

    const registered = trend(lines, "registered", false);
    expect(registered.unit).toBe("year");
    expect(registered.periods[0]).toEqual({ key: "1991", label: "1991" });
    expect(registered.byKind.minor.at(-1)).toBe(3);

    const open = trend(lines, "open", false);
    // 2026's open is November's, its last month, not January's and November's together.
    expect(open.byKind.minor.at(-1)).toBe(2);
  });

  it("weighs by weight when asked", () => {
    expect(trend([month("2026-10", "major", { settled: 1, settled_weight: 3 })], "settled", true).byKind.major).toEqual([3]);
  });

  it("has nothing to show with no lines", () => {
    expect(trend([], "registered", false).periods).toEqual([]);
  });
});

describe("network", () => {
  const nodes = [node("agnes", "Toreador"), node("bram", "Brujah: Anarch"), node("cora", "Ventrue", { titles: ["Prince"] }), node("dov", "Ventrue")];
  const links = [link("agnes", "bram", { major: 1, minor: 1 }), link("cora", "agnes", { trivial: 1 }), link("dov", "cora", { life: 1 })];
  const all = { clan: null, sect: null, court: false, kinds: ALL, minWeight: 0 };

  it("keeps every link with someone of the clan on either side, and the people at their ends", () => {
    const found = network(nodes, links, { ...all, clan: "Brujah" }, WEIGHTS);

    expect(found.links.map((l) => [l.debtor, l.creditor])).toEqual([["agnes", "bram"]]);
    expect(found.nodes.map((n) => n.who.key)).toEqual(["agnes", "bram"]);
  });

  it("weighs a link by the kinds shown, colours it by the heaviest, and drops what's too light", () => {
    const found = network(nodes, links, { ...all, kinds: new Set(["minor", "trivial"] as const), minWeight: 1 }, WEIGHTS);

    expect(found.links).toHaveLength(1);
    expect(found.links[0]).toMatchObject({ debtor: "agnes", shown: 1, kind: "minor" });
  });

  it("keeps the court's debts", () => {
    const found = network(nodes, links, { ...all, court: true }, WEIGHTS);

    expect(found.links.map((l) => l.debtor).sort()).toEqual(["cora", "dov"]);
  });

  it("hides the lightest links once there are too many to read", () => {
    const many = Array.from({ length: 5 }, (_, i) => ({ ...links[0]!, weight: i + 1 }));
    expect(readableMinimum(many, 10)).toBe(0);
    expect(readableMinimum(many, 3)).toBe(3);
  });
});

describe("flows", () => {
  const flow = {
    groups: ["Toreador", "Brujah", "Ventrue"],
    matrix: [
      [1, 3, 0],
      [1, 0, 2],
      [0, 0, 0],
    ],
    counts: [
      [1, 1, 0],
      [1, 0, 1],
      [0, 0, 0],
    ],
  };

  it("folds the lightest groups into Other", () => {
    const found = folded(flow, 2);

    expect(found.groups).toEqual(["Toreador", "Other"]);
    expect(found.matrix).toEqual([
      [1, 3],
      [1, 2],
    ]);
  });

  it("lists each pair once with what runs each way", () => {
    expect(flowPairs(flow)).toEqual([
      { from: "Toreador", to: "Brujah", owed: 3, back: 1, boons: 2 },
      { from: "Brujah", to: "Ventrue", owed: 2, back: 0, boons: 1 },
      { from: "Toreador", to: "Toreador", owed: 1, back: 0, boons: 1 },
    ]);
  });
});

describe("timeline", () => {
  it("puts the games oldest first", () => {
    const game = (id: string, starts_at: string) => ({
      game: { id, starts_at, ends_at: starts_at },
      registered: 0,
      registered_weight: 0,
      by_kind: {},
      settled: 0,
      settled_weight: 0,
      most_active: [],
    });

    expect(timeline([game("b", "2026-10-03T22:00:00Z"), game("a", "2026-09-05T22:00:00Z")]).map((g) => g.game.id)).toEqual(["a", "b"]);
  });
});
