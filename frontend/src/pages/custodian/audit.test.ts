import { describe, expect, it } from "vitest";
import { datesFor } from "../../dates";
import { auditQuery, exportHref, filtersFrom, nextDay, NO_FILTERS, toParams } from "./audit";

describe("the audit search's filters", () => {
  it("go in the address and come back out of it", () => {
    const filters = { ...NO_FILTERS, person: "night_owl", words: " Brawl " };
    expect(toParams(filters)).toEqual({ person: "night_owl", words: "Brawl" });
    expect(filtersFrom(new URLSearchParams(toParams(filters)))).toEqual({ ...filters, words: "Brawl" });
    expect(filtersFrom(new URLSearchParams())).toEqual(NO_FILTERS);
  });

  it("take the days whole, on the custodian's clock", () => {
    const { fromInput } = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });
    const query = auditQuery({ ...NO_FILTERS, from: "2026-10-01", to: "2026-11-01" }, fromInput);
    expect(query.since).toBe("2026-10-01T04:00:00.000Z");
    // The last day included: until the midnight after it, once summer time has ended.
    expect(query.until).toBe("2026-11-02T05:00:00.000Z");
    expect(auditQuery(NO_FILTERS, fromInput)).toEqual({});
  });

  it("know the day after the end of a month and a year", () => {
    expect(nextDay("2026-10-31")).toBe("2026-11-01");
    expect(nextDay("2026-12-31")).toBe("2027-01-01");
    expect(nextDay("2028-02-28")).toBe("2028-02-29");
  });

  it("export only what is set", () => {
    expect(exportHref(auditQuery(NO_FILTERS, () => new Date()))).toBe("/api/audit/export");
    expect(exportHref(auditQuery({ ...NO_FILTERS, group: "xp", words: "awarded 3" }, () => new Date()))).toBe("/api/audit/export?group=xp&q=awarded+3");
  });
});
