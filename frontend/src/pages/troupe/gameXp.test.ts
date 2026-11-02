import { describe, expect, it } from "vitest";
import type { GameXpSettings } from "../../api/types";
import { addBand, adjustmentText, bandLabel, capText, DEFAULTS, figureFor, fromRows, isBookWay, NO_CHOICE, PRESETS, removeBand, signed, toRows, usesLeft } from "./gameXp";

const ait = PRESETS.find((p) => p.name === "AIT taper")!.bands;
const helped = { key: "h", name: "Helped", amount: 1, per_month: 1 };
const unfindable = { key: "n", name: "Not findable", amount: -1, per_month: null };
const chart: GameXpSettings = { ...DEFAULTS, bands: ait, adjustments: [helped, unfindable] };

describe("the chart's words", () => {
  it("labels each band from the one before, the last with no top", () => {
    expect(ait.map((_, i) => bandLabel(ait, i))).toEqual(["0–200", "201–300", "301–400", "401–500", "501+"]);
  });

  it("names adjustments and the cap as players read them", () => {
    expect(signed(2)).toBe("+2");
    expect(signed(-1)).toBe("−1");
    expect(adjustmentText(helped)).toBe("Helped +1, once a month");
    expect(adjustmentText(unfindable)).toBe("Not findable −1");
    expect(adjustmentText({ name: "Costumed", amount: 1, per_month: 3 })).toBe("Costumed +1, 3 times a month");
    expect(capText({ cap: "warn", monthly_xp: null })).toBe("Warned past 10 a month, never refused");
    expect(capText({ cap: "cap", monthly_xp: 12 })).toBe("Capped at 12 a month: the excess isn't given");
    expect(capText({ cap: "off", monthly_xp: 12 })).toBe("Not limited");
  });

  it("knows the book's way, which is the default", () => {
    expect(isBookWay(DEFAULTS)).toBe(true);
    expect(isBookWay(chart)).toBe(false);
    expect(isBookWay({ ...DEFAULTS, absentee: true })).toBe(false);
    expect(isBookWay({ ...DEFAULTS, cap: "off" })).toBe(false);
  });
});

describe("the chart editor", () => {
  it("round-trips a preset through its rows", () => {
    expect(fromRows(toRows(ait))).toEqual({ bands: ait, error: null });
    expect(fromRows([])).toEqual({ bands: [], error: null });
  });

  it("refuses bands that don't rise, or figures that aren't whole numbers", () => {
    const rows = toRows(ait);
    expect(fromRows(rows.map((r, i) => (i === 1 ? { ...r, upTo: "150" } : r))).error).toBe("Band 2 must go higher than the one before.");
    expect(fromRows(rows.map((r, i) => (i === 0 ? { ...r, upTo: "" } : r))).error).toBe("Give band 1 the earned XP it goes up to.");
    expect(fromRows(rows.map((r, i) => (i === 2 ? { ...r, attended: "2.5" } : r))).error).toBe("Give band 3 its XP as whole numbers.");
    // The last band never needs a top.
    expect(fromRows([{ upTo: "", attended: "3", absentee: "2" }]).bands).toEqual([{ up_to: null, attended: 3, absentee: 2 }]);
  });

  it("adds a band before the open one, and keeps the last open when one is taken away", () => {
    const first = addBand([]);
    expect(first).toEqual([{ upTo: "", attended: "5", absentee: "4" }]);
    const two = addBand(first);
    expect(two.map((r) => r.upTo)).toEqual(["100", ""]);
    expect(addBand(toRows(ait)).map((r) => r.upTo)).toEqual(["200", "300", "400", "500", "600", ""]);
    const trimmed = removeBand(toRows(ait), 4);
    expect(trimmed.map((r) => r.upTo)).toEqual(["200", "300", "400", ""]);
    expect(fromRows(trimmed).bands?.at(-1)).toEqual({ up_to: null, attended: 2, absentee: 1 });
    expect(removeBand(toRows(ait), 1).map((r) => r.upTo)).toEqual(["200", "400", "500", ""]);
  });
});

describe("a character's figure when awarding", () => {
  const flat = { attended: 8, absentee: 6 };

  it("is the chart's figure for its band and kind, or the flat amounts with no chart", () => {
    expect(figureFor(chart, { kind: "attended", figure: 4, month_xp: 0 }, flat, NO_CHOICE)).toEqual({ figure: 4, amount: 4, capped: 0 });
    expect(figureFor(DEFAULTS, { kind: "attended", figure: null, month_xp: 0 }, flat, NO_CHOICE).amount).toBe(8);
    expect(figureFor(DEFAULTS, { kind: "absentee", figure: null, month_xp: 0 }, flat, NO_CHOICE).amount).toBe(6);
  });

  it("adds the adjustments ticked, never below nothing", () => {
    expect(figureFor(chart, { kind: "attended", figure: 5, month_xp: 0 }, flat, { ...NO_CHOICE, ticks: ["h"] }).amount).toBe(6);
    expect(figureFor(chart, { kind: "absentee", figure: 0, month_xp: 0 }, flat, { ...NO_CHOICE, ticks: ["n"] }).amount).toBe(0);
  });

  it("is held back by the cap only while the troupe caps, and not when set by hand", () => {
    const line = { kind: "attended" as const, figure: 5, month_xp: 7 };
    expect(figureFor({ ...chart, cap: "cap" }, line, flat, NO_CHOICE)).toEqual({ figure: 5, amount: 3, capped: 2 });
    expect(figureFor({ ...chart, cap: "cap", monthly_xp: 20 }, line, flat, NO_CHOICE).capped).toBe(0);
    expect(figureFor({ ...chart, cap: "warn" }, line, flat, NO_CHOICE).amount).toBe(5);
    expect(figureFor({ ...chart, cap: "cap" }, line, flat, { ticks: [], override: 5, reason: "Ran a scene" })).toEqual({ figure: 5, amount: 5, capped: 0 });
  });

  it("counts an adjustment's uses left this month", () => {
    expect(usesLeft(helped, { used: {} })).toBe(1);
    expect(usesLeft(helped, { used: { h: 1 } })).toBe(0);
    expect(usesLeft(unfindable, { used: { n: 4 } })).toBeNull();
  });
});
