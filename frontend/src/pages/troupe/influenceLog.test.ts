import { describe, expect, it } from "vitest";
import { datesFor } from "../../dates";
import { logQuery, NO_FILTERS, nextDay, sourceText, whoText } from "./influenceLog";

const dates = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });

describe("the influence log page", () => {
  it("counts days in the reader's zone, the last one included", () => {
    expect(nextDay("2026-12-31")).toBe("2027-01-01");
    expect(logQuery({ ...NO_FILTERS, from: "2026-07-11", to: "2026-07-11" }, dates)).toMatchObject({
      since: "2026-07-11T04:00:00.000Z",
      until: "2026-07-12T04:00:00.000Z",
    });
  });

  it("filters by a character, or by someone not in Horatio", () => {
    expect(logQuery({ ...NO_FILTERS, who: "c:123" }, dates)).toMatchObject({ character_id: "123", name: undefined });
    expect(logQuery({ ...NO_FILTERS, who: "n:REDACTED" }, dates)).toMatchObject({ character_id: undefined, name: "REDACTED" });
  });

  it("names who took it as it was logged, and says when they have changed or left", () => {
    expect(whoText({ name: "Agnes", current_name: null, left_troupe: false })).toBe("Agnes");
    expect(whoText({ name: "Agnes", current_name: "Agnes Duval", left_troupe: true })).toBe("Agnes (now Agnes Duval) (left the troupe)");
  });

  it("says where it came from", () => {
    expect(sourceText({ source: "downtime", cycle_name: "November", reference: null })).toBe("Downtime: November");
    expect(sourceText({ source: "import", cycle_name: null, reference: "E334" })).toBe("Imported (E334)");
    expect(sourceText({ source: "hand", cycle_name: null, reference: null })).toBe("By hand");
  });
});
