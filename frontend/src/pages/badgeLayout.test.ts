import { describe, expect, it } from "vitest";
import { BADGE_SIZES, grid, nameSize, pages, perPageText, standing } from "./badgeLayout";

describe("badge sheets", () => {
  it("hold as many badges as fit the paper", () => {
    expect(grid("3x5", "letter")).toEqual({ columns: 2, rows: 2, perPage: 4 });
    expect(grid("3x4", "letter").perPage).toBe(4);
    expect(grid("cr80", "letter")).toEqual({ columns: 3, rows: 3, perPage: 9 });
    expect(grid("4x6", "letter")).toEqual({ columns: 2, rows: 1, perPage: 2 });
    // A4 is a little narrower and taller: two 4 × 6 in badges no longer fit across.
    expect(grid("3x5", "a4").perPage).toBe(4);
    expect(grid("cr80", "a4").perPage).toBe(9);
    expect(grid("4x6", "a4")).toEqual({ columns: 1, rows: 1, perPage: 1 });
    expect(perPageText(9, "letter")).toBe("nine to each US Letter page");
  });

  it("go in pages, the last perhaps short", () => {
    expect(pages([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    expect(pages([], 9)).toEqual([]);
  });

  it("make the name as big as fits", () => {
    expect(nameSize("Agnes")).toBe(28);
    expect(nameSize("Agnes Moreau")).toBe(28);
    expect(nameSize("Bartholomew")).toBe(24);
    expect(nameSize("Wilhelmina Vandersteen-Harrow")).toBeLessThan(nameSize("Agnes Moreau"));
    expect(nameSize("Constantinopolitanus")).toBe(14);
    // Smaller on smaller badges, larger on larger, and always bigger than the line under it.
    expect(nameSize("Agnes", "cr80")).toBeLessThan(nameSize("Agnes"));
    expect(nameSize("Agnes", "4x6")).toBeGreaterThan(nameSize("Agnes"));
    expect(nameSize("Constantinopolitanus", "cr80")).toBeGreaterThan(12.5 * BADGE_SIZES.cr80.text);
  });

  it("say clan and social age", () => {
    expect(standing("Toreador", "Ancilla")).toBe("Toreador · Ancilla");
    expect(standing(null, "Neonate")).toBe("Neonate");
  });
});
