import { describe, expect, it } from "vitest";
import { chartFor, ratingsOf, readFigures, startingFigures } from "./languages";

describe("startingFigures", () => {
  it("starts from the troupe's own chart, else the chart in use, one figure per rating", () => {
    expect(startingFigures({ custom: [2, 5], table: [1, 2, 3, 4], max_rating: 4 })).toEqual(["2", "5", "5", "5"]);
    expect(startingFigures({ custom: [], table: [1, 2, 4, 8, 16], max_rating: 3 })).toEqual(["1", "2", "4"]);
  });
});

describe("readFigures", () => {
  it("reads whole numbers that never go down", () => {
    expect(readFigures(["1", " 3 ", "3"])).toEqual({ table: [1, 3, 3], error: null });
  });

  it("says what is wrong", () => {
    expect(readFigures(["1", ""]).error).toBe("Give Linguistics 2 a whole number of languages from 0 to 999.");
    expect(readFigures(["1.5"]).error).toMatch(/whole number/);
    expect(readFigures(["1000"]).error).toMatch(/0 to 999/);
    expect(readFigures(["4", "2"]).error).toBe("Linguistics 2 cannot give fewer languages than Linguistics 1.");
  });
});

describe("ratingsOf", () => {
  it("carries a chart's last figure on, or gives one a dot by the book", () => {
    expect(ratingsOf([1, 2, 4], 5)).toEqual([1, 2, 4, 4, 4]);
    expect(ratingsOf(null, 3)).toEqual([1, 2, 3]);
  });
});

describe("chartFor", () => {
  it("plays the preset, the custom figures or the book", () => {
    expect(chartFor("accelerated", [1, 2, 4], [9])).toEqual([1, 2, 4]);
    expect(chartFor("custom", [1, 2, 4], [9])).toEqual([9]);
    expect(chartFor("book", [1, 2, 4], [9])).toBeNull();
  });
});
