import { describe, expect, it } from "vitest";
import { nameSize, pages, standing } from "./badgeLayout";

describe("badge sheets", () => {
  it("hold two badges to a page", () => {
    expect(pages([1, 2, 3, 4, 5])).toEqual([[1, 2], [3, 4], [5]]);
    expect(pages([])).toEqual([]);
  });

  it("make the name as big as fits", () => {
    expect(nameSize("Agnes")).toBe(28);
    expect(nameSize("Agnes Moreau")).toBe(28);
    expect(nameSize("Bartholomew")).toBe(24);
    expect(nameSize("Wilhelmina Vandersteen-Harrow")).toBeLessThan(nameSize("Agnes Moreau"));
    expect(nameSize("Constantinopolitanus")).toBe(14);
  });

  it("say clan and social age", () => {
    expect(standing("Toreador", "Ancilla")).toBe("Toreador · Ancilla");
    expect(standing(null, "Neonate")).toBe("Neonate");
  });
});
