import { describe, expect, it } from "vitest";
import { everyone, nudge, totals } from "./xpAwards";

describe("bulk XP awards", () => {
  it("sets everyone, nudges one, and adds up who gets something", () => {
    let amounts = everyone(["a", "b", "c"], 8);
    amounts = nudge(amounts, "b", 2);
    amounts = nudge(amounts, "c", -8);
    amounts = nudge(amounts, "c", -1);
    expect(amounts).toEqual({ a: 8, b: 10, c: 0 });
    expect(totals(amounts)).toEqual({ characters: 2, total: 18 });
  });
});
