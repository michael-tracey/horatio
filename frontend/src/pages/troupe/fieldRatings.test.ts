import { describe, expect, it } from "vitest";
import { fieldRatings } from "./AllowancesSection";

describe("fieldRatings", () => {
  it("reads the rating each further field needs", () => {
    expect(fieldRatings("1, 3, 5")).toEqual([1, 3, 5]);
    expect(fieldRatings("1 3")).toEqual([1, 3]);
    expect(fieldRatings("")).toEqual([]);
  });

  it("refuses what is not a rating", () => {
    expect(fieldRatings("1, three")).toBeNull();
    expect(fieldRatings("0")).toBeNull();
  });
});
