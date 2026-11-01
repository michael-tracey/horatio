import { describe, expect, it } from "vitest";
import { simpleChallenge, suggestedCards, throwChallenges } from "./feedingRules";

describe("suggestedCards", () => {
  it("follows the book's table and its adjustments, fractions rounded up", () => {
    expect([10, 20, 30, 40].map((n) => suggestedCards(n))).toEqual([14, 28, 42, 56]);
    expect(suggestedCards(20, "severe")).toBe(20);
    expect(suggestedCards(10, "none", "very")).toBe(19);
    expect(suggestedCards(0)).toBe(0);
  });
});

describe("throwChallenges", () => {
  it("is a win, tie or loss, a third each", () => {
    expect([0, 0.4, 0.9].map((n) => simpleChallenge(() => n))).toEqual(["win", "tie", "lose"]);
  });

  it("catches a poacher by each patroller with a lost challenge among their actions", () => {
    const throws = [0.1, 0.9, 0.5, 0.5];
    const random = () => throws.shift()!;
    // Agnes's two actions: a win and a loss; Bram's two: ties.
    expect(
      throwChallenges(
        [
          { character_id: "agnes", actions: 2 },
          { character_id: "bram", actions: 2 },
        ],
        random,
      ),
    ).toEqual(["agnes"]);
  });
});
