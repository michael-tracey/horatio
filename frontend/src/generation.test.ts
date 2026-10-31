import { describe, expect, it } from "vitest";
import { dots, generationText } from "./generation";

describe("generationText", () => {
  it("names the generation where it is known, never the bare rating", () => {
    expect(generationText(1, 11)).toBe("11th generation");
    expect(generationText(1, 12)).toBe("12th generation");
    expect(generationText(5, 6)).toBe("6th generation");
  });

  it("falls back to the background's dots", () => {
    expect(generationText(1)).toBe("Generation background ●");
    expect(generationText(2, null)).toBe("Generation background ●●");
    expect(generationText(0)).toBe("no Generation background");
  });

  it("can give both, for staff accepting a character", () => {
    expect(generationText(2, 10, true)).toBe("10th generation (Generation background ●●)");
    expect(generationText(1, null, true)).toBe("Generation background ●");
  });

  it("never reads as Caine", () => {
    for (let rating = 0; rating <= 5; rating++) {
      expect(generationText(rating)).not.toMatch(/Generation \d/);
    }
  });
});

describe("dots", () => {
  it("draws a rating", () => {
    expect(dots(3)).toBe("●●●");
    expect(dots(0)).toBe("");
  });
});
