import { describe, expect, it } from "vitest";
import { memberSince } from "./players";

const now = new Date(2026, 9, 19);

describe("memberSince", () => {
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
