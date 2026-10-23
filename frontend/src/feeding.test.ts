import { describe, expect, it } from "vitest";
import type { FeedingNeedOut } from "./api/types";
import { emptyFeeding, herdShared, needText, tally } from "./feeding";

const need: FeedingNeedOut = {
  needed: 2,
  herd_factor: 1,
  always_half: false,
  lines: [
    { source: "Gangrel", amount: 1, kind: "clan", note: "", page: null, text: "Gangrel 1" },
    { source: "Disease Carrier", amount: 1, kind: "trait", note: "", page: "262", text: "Disease Carrier +1" },
  ],
};

describe("feeding", () => {
  it("gives the number and its reasons", () => {
    expect(needText(need)).toEqual({ needed: 2, reasons: "Gangrel 1 · Disease Carrier +1" });
  });

  it("counts feeding actions, the character's Herd and gifts", () => {
    const answer = { ...emptyFeeding(), actions: 1, herd_own: 1 };
    const t = tally(need, answer, [{ character_name: "Bram", amount: 2, submitted: true }]);
    expect(t.text).toBe("Feeding 1 + your Herd 1 + 2 from Bram = 4 of 2 needed ✓");
    expect(t.enough).toBe(true);
  });

  it("says when it falls short, without blocking", () => {
    const t = tally(need, { ...emptyFeeding(), actions: 1 }, []);
    expect(t.text).toBe("Feeding 1 = 1 of 2 needed: you'll come to game at half Blood unless staff say otherwise.");
    expect(t.enough).toBe(false);
  });

  it("counts Herd as the character's traits say", () => {
    const doubled = tally({ ...need, herd_factor: 2 }, { ...emptyFeeding(), herd_own: 1 }, []);
    expect(doubled.total).toBe(2);
    const none = tally({ ...need, herd_factor: 0, always_half: true }, { ...emptyFeeding(), actions: 3, herd_own: 2 }, []);
    expect(none.total).toBe(3);
    expect(none.enough).toBe(false);
  });

  it("adds up the Herd shared out", () => {
    expect(
      herdShared({ ...emptyFeeding(), herd_own: 1, gifts: [{ character_id: "b", amount: 2 }], herd_saved: 1, herd_other: 1 }),
    ).toBe(5);
  });
});
