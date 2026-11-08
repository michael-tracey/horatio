import { describe, expect, it } from "vitest";
import { xpTotal } from "./xpTotals";

describe("xpTotal", () => {
  it("shows a negative total with a minus sign", () => {
    expect([xpTotal(12), xpTotal(0), xpTotal(-3)]).toEqual(["12", "0", "−3"]);
  });
});
