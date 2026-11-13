import { describe, expect, it } from "vitest";
import { extent, gameDate, lanes, placed, rangeOf, rows, type ChronicleEvent } from "./chronicle";

const event = (over: Partial<ChronicleEvent>): ChronicleEvent => ({
  key: over.key ?? "k",
  kind: "status",
  character_id: "c1",
  character_name: "Agnes",
  clan: "Ventrue",
  label: "Loyal",
  detail: "",
  at: "2026-10-03T20:00:00Z",
  on: null,
  ends_at: null,
  ends_on: null,
  ongoing: false,
  ...over,
});

const NOW = new Date("2026-11-13T00:00:00Z");

describe("placing events", () => {
  it("reads an in-game date centuries back", () => {
    expect(gameDate("1791-06-02").toISOString()).toBe("1791-06-02T00:00:00.000Z");
    expect(gameDate("0800-01-01").getUTCFullYear()).toBe(800);
  });

  it("uses Horatio's time unless asked for in-game dates", () => {
    const e = event({ on: "1890-03-01" });
    expect(placed([e], false).shown[0]!.from.toISOString()).toBe("2026-10-03T20:00:00.000Z");
    expect(placed([e], true).shown[0]!.from.toISOString()).toBe("1890-03-01T00:00:00.000Z");
  });

  it("lists events without an in-game date instead of placing them", () => {
    const joined = event({ key: "j", kind: "arrival" });
    const title = event({ key: "t", kind: "title", on: "1990-01-01", ends_at: "2026-01-01T00:00:00Z", ends_on: null });
    const { shown, undated } = placed([joined, title], true);
    expect(shown).toHaveLength(0);
    expect(undated.map((e) => e.key)).toEqual(["j", "t"]);
  });

  it("draws a title as a span, open while it is held", () => {
    const held = event({ kind: "title", ongoing: true });
    const p = placed([held], false).shown[0]!;
    expect(p.span).toBe(true);
    expect(p.to).toBeNull();
  });
});

describe("lanes and rows", () => {
  const at = (iso: string) => new Date(iso);
  it("stacks spans at the same time and lets moments share a lane", () => {
    const items = [
      { from: at("2000-01-01"), to: at("2010-01-01"), span: true },
      { from: at("2005-01-01"), to: null, span: true },
      { from: at("2011-01-01"), to: null, span: false },
      { from: at("2011-01-01"), to: null, span: false },
    ];
    const { placed: out, count } = lanes(items, NOW);
    expect(count).toBe(2);
    expect(out.map((o) => o.lane)).toEqual([0, 1, 0, 0]);
  });

  it("groups by kind in a fixed order, or by character as they first appear", () => {
    const shown = placed(
      [
        event({ key: "a", kind: "death", character_id: "c2", character_name: "Lena", at: "2026-01-01T00:00:00Z" }),
        event({ key: "b", kind: "title", at: "2025-01-01T00:00:00Z" }),
        event({ key: "c", kind: "status", at: "2024-01-01T00:00:00Z" }),
      ],
      false,
    ).shown;
    expect(rows(shown, "kind", NOW).map((r) => r.label)).toEqual(["Titles", "Status", "Deaths"]);
    expect(rows(shown, "character", NOW).map((r) => r.label)).toEqual(["Agnes", "Lena"]);
  });
});

describe("the time shown", () => {
  it("covers everything with a little room, at least a few days", () => {
    const shown = placed([event({ at: "2026-10-03T20:00:00Z" })], false).shown;
    const [start, end] = extent(shown, NOW);
    expect(end.getTime() - start.getTime()).toBeGreaterThanOrEqual(4 * 86_400_000);
  });

  it("narrows to the last years, never past all of it", () => {
    const all: [Date, Date] = [gameDate("1791-01-01"), NOW];
    expect(rangeOf(all, "decade")[0].getUTCFullYear()).toBe(2016);
    expect(rangeOf(all, "all")).toEqual(all);
    const short: [Date, Date] = [new Date("2026-06-01T00:00:00Z"), NOW];
    expect(rangeOf(short, "century")[0]).toEqual(short[0]);
  });
});
