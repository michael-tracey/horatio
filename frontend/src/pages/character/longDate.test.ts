import { describe, expect, it } from "vitest";
import { longDate } from "./longDate";

describe("longDate", () => {
  it("reads the day as that day, not midnight UTC in the reader's time zone", () => {
    const options = { day: "numeric", month: "long", year: "numeric" } as const;
    expect(longDate("2027-01-19")).toBe(new Date(2027, 0, 19).toLocaleDateString(undefined, options));
    expect(longDate("2027-01-01")).toMatch(/2027/);
  });
});
