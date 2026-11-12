import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, months, net, netWords, share, weight, weightsLine } from "./boonStandings";

describe("boon standings", () => {
  it("writes weights as short as they go", () => {
    expect([weight(3), weight(1.5), weight(0.25), weight(2.333)]).toEqual(["3", "1.5", "0.25", "2.33"]);
  });

  it("signs a net, with a true minus sign, and says it in words", () => {
    expect([net(2), net(-1.5), net(0)]).toEqual(["+2", "−1.5", "0"]);
    expect(netWords(-1.5)).toBe("owes 1.5 more than they're owed");
    expect(netWords(0)).toBe("even");
  });

  it("measures a bar against the longest, never past it or below nothing", () => {
    expect([share(5, 10), share(10, 10), share(0, 10), share(3, 0), share(12, 10)]).toEqual([50, 100, 0, 0, 100]);
  });

  it("lists the weights in the kinds' order", () => {
    expect(weightsLine(DEFAULT_WEIGHTS)).toBe("Trivial 0.5 · Minor 1 · Major 3 · Blood 5 · Life 10");
  });

  it("says how long boons take to settle", () => {
    expect([months(null), months(0), months(1), months(2.5)]).toEqual(["—", "under a month", "1 month", "2.5 months"]);
  });
});
