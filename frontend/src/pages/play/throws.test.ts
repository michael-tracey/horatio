import { describe, expect, it } from "vitest";
import { COUNT_IN, countIn, fairIndex, fairThrow, readThrows, remember, THROWS, type Thrown } from "./throws";

describe("a fair throw", () => {
  it("comes up rock, paper and scissors a third of the time each, over many throws", () => {
    const count = { rock: 0, paper: 0, scissors: 0 };
    const n = 30_000;
    for (let i = 0; i < n; i++) count[fairThrow()]++;
    // Three standard deviations of a third is about 0.008 at this many throws.
    for (const t of THROWS) expect(Math.abs(count[t] / n - 1 / 3)).toBeLessThan(0.02);
  });

  it("draws again from the uneven top of the range, rather than favour the low numbers", () => {
    // 2³² is one more than a multiple of 3: the last value would give rock once too often.
    const draws = [2 ** 32 - 1, 2 ** 32 - 1, 7];
    const random = () => draws.shift()!;
    expect(fairIndex(3, random)).toBe(1);
    expect(draws).toEqual([]);
    // Every value kept is in a range that splits evenly.
    expect((2 ** 32 - 1) % 3).toBe(0);
    expect(fairIndex(3, () => 2 ** 32 - 2)).toBe(2);
  });

  it("names each throw by its draw", () => {
    expect([0, 1, 2, 3].map((d) => fairThrow(() => d))).toEqual(["rock", "paper", "scissors", "rock"]);
  });
});

describe("the count-in", () => {
  it("says rock, paper, scissors before the throw, or nothing with reduced motion", () => {
    expect(countIn(false)).toEqual(COUNT_IN);
    expect(countIn(true)).toEqual([]);
  });
});

describe("the last throws", () => {
  const at = (i: number) => `2026-11-11T21:0${i}:00.000Z`;
  it("keeps the newest three, newest first", () => {
    let past: Thrown[] = [];
    for (const [i, t] of (["rock", "paper", "scissors", "paper"] as const).entries()) past = remember(past, { throw: t, at: at(i) });
    expect(past.map((t) => t.throw)).toEqual(["paper", "scissors", "paper"]);
  });

  it("reads only what it kept, whatever storage holds", () => {
    expect(readThrows(null)).toEqual([]);
    expect(readThrows("not json")).toEqual([]);
    expect(readThrows('{"throw":"rock"}')).toEqual([]);
    expect(readThrows(JSON.stringify([{ throw: "lizard", at: at(1) }, { throw: "rock", at: at(2) }, null]))).toEqual([{ throw: "rock", at: at(2) }]);
  });
});
