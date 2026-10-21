import { describe, expect, it } from "vitest";
import { datesFor } from "../dates";
import { memberSince as since } from "./players";

const now = new Date(2026, 9, 19);
const dates = datesFor({ time_zone: null, date_format: "day_month", clock: "12" });
const memberSince = (joined: string, at: Date) => since(joined, dates, at);

describe("memberSince", () => {
  it("names the month in the person's format", () => {
    expect(memberSince(new Date(2019, 2, 4).toISOString(), now)).toBe("March 2019 (7 years)");
    expect(since(new Date(2019, 2, 4).toISOString(), datesFor({ time_zone: null, date_format: "iso", clock: "24" }), now)).toBe("2019-03 (7 years)");
  });

  it("counts whole years", () => {
    expect(memberSince(new Date(2019, 2, 4).toISOString(), now)).toMatch(/2019 \(7 years\)$/);
    expect(memberSince(new Date(2025, 9, 19).toISOString(), now)).toMatch(/\(1 year\)$/);
  });

  it("counts months in the first year", () => {
    expect(memberSince(new Date(2026, 6, 1).toISOString(), now)).toMatch(/\(3 months\)$/);
    expect(memberSince(new Date(2025, 9, 20).toISOString(), now)).toMatch(/\(11 months\)$/);
  });

  it("calls a brand new account new", () => {
    expect(memberSince(new Date(2026, 9, 2).toISOString(), now)).toMatch(/\(new this month\)$/);
  });
});
