import { describe, expect, it } from "vitest";
import { drinkMost, drinkReminder, poolBoxes } from "./vitae";

const vitae = { pool: 10, human: 5, human_start: 5, last_drank_at: null, days: 30 };

describe("a ghoul's pool", () => {
  it("is its vitae, then human Blood, then what it spent", () => {
    expect(poolBoxes({ blood: { value: 3, most: 5, start: 5 }, vitae })).toEqual([
      ...Array(3).fill("vitae"),
      ...Array(5).fill("human"),
      ...Array(2).fill("spent"),
    ]);
    expect(poolBoxes({ blood: { value: 3, most: 5, start: 5 }, vitae: null })).toEqual([]);
  });

  it("takes a drink of what it lacks, and at least 1 to keep the month", () => {
    expect(drinkMost({ blood: { value: 2, most: 5, start: 5 } })).toBe(3);
    expect(drinkMost({ blood: { value: 5, most: 5, start: 5 } })).toBe(1);
  });
});

describe("the monthly drink", () => {
  const now = new Date("2026-10-26T20:00:00Z");
  it("counts from the last drink", () => {
    expect(drinkReminder("2026-10-24T20:00:00Z", 30, now)).toEqual({ level: "ok", text: "Last drank vitae 2 days ago." });
    expect(drinkReminder("2026-10-01T20:00:00Z", 30, now).level).toBe("near");
    expect(drinkReminder("2026-10-01T20:00:00Z", 30, now).text).toContain("Drink within 5 days");
    expect(drinkReminder("2026-09-20T20:00:00Z", 30, now).level).toBe("over");
  });

  it("asks for a first drink when none is recorded", () => {
    expect(drinkReminder(null, 30, now).text).toContain("No drink of vitae recorded yet");
  });
});
