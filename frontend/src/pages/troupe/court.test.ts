import { describe, expect, it } from "vitest";
import { courtRows, dated, lanes, statusExtent, type CourtHolding } from "./court";

function holding(over: Partial<CourtHolding>): CourtHolding {
  return {
    id: over.id ?? crypto.randomUUID(),
    title: "Prince",
    character_id: null,
    character_name: "Varga",
    clan: "Ventrue",
    began_at: "2026-01-01T00:00:00Z",
    ended_at: null,
    began_in_game: null,
    ended_in_game: null,
    began_how: "given",
    ended_how: null,
    backfilled: false,
    ...over,
  };
}

const NOW = new Date("2026-06-01T00:00:00Z");

describe("dated", () => {
  it("draws real dates, with no end while it is held", () => {
    const [d] = dated([holding({ ended_at: null })], false);
    expect(d!.from.toISOString()).toBe("2026-01-01T00:00:00.000Z");
    expect(d!.to).toBeNull();
  });

  it("in game, leaves out a holding staff haven't dated, and reaches back centuries", () => {
    const shown = dated(
      [
        holding({ began_in_game: "1791-03-01", ended_at: "2026-02-01T00:00:00Z", ended_in_game: "1888-10-31" }),
        holding({ began_in_game: null }),
        // Ended, but only its start dated in game: it can't be placed.
        holding({ began_in_game: "1900-01-01", ended_at: "2026-02-01T00:00:00Z" }),
        holding({ began_in_game: "1999-12-31" }),
      ],
      true,
    );
    expect(shown.map((d) => [d.from.getUTCFullYear(), d.to?.getUTCFullYear() ?? null])).toEqual([
      [1791, 1888],
      [1999, null],
    ]);
  });
});

describe("lanes", () => {
  it("stacks holders at the same time and lets one after another share a lane", () => {
    const items = dated(
      [
        holding({ id: "a", began_at: "2026-01-01T00:00:00Z", ended_at: "2026-02-01T00:00:00Z" }),
        holding({ id: "b", began_at: "2026-01-15T00:00:00Z", ended_at: null }),
        holding({ id: "c", began_at: "2026-02-01T00:00:00Z", ended_at: "2026-03-01T00:00:00Z" }),
      ],
      false,
    );
    const { placed, count } = lanes(items, NOW);
    expect(Object.fromEntries(placed.map((p) => [p.dates.holding.id, p.lane]))).toEqual({ a: 0, b: 1, c: 0 });
    expect(count).toBe(2);
  });

  it("gives an empty row one lane", () => {
    expect(lanes([], NOW).count).toBe(1);
  });
});

describe("courtRows", () => {
  it("keeps court order, groups by sect with a heading on each sect's first row, and leaves out titles with nothing to draw", () => {
    const titles = [
      { name: "Prince", sect: "Camarilla" },
      { name: "Harpy", sect: "Camarilla" },
      { name: "Baron", sect: "Anarch Movement" },
      { name: "Soldier", sect: null },
    ];
    const shown = dated([holding({ title: "Prince" }), holding({ title: "Harpy" }), holding({ title: "Soldier" })], false);

    const rows = courtRows(titles, shown);

    expect(rows.map((r) => [r.name, r.sectStart])).toEqual([
      ["Prince", "Camarilla"],
      ["Harpy", null],
      ["Soldier", "Other titles"],
    ]);
  });
});

describe("statusExtent", () => {
  it("shares one scale: from the earliest point to now, up to the most held at once", () => {
    const lines = [
      { character_id: "a", name: "Agnes", clan: null, gained: 1, lost: 0, points: [{ at: "2026-02-01T00:00:00Z", fleeting: 1, negative: 2 }] },
      { character_id: "b", name: "Bram", clan: null, gained: 0, lost: 0, points: [{ at: "2026-01-01T00:00:00Z", fleeting: 0, negative: 0 }] },
    ];
    const { start, end, most } = statusExtent(lines, NOW);
    expect(start.toISOString()).toBe("2026-01-01T00:00:00.000Z");
    expect(end).toBe(NOW);
    expect(most).toBe(3);
  });
});
