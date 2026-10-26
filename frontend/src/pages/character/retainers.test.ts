import { describe, expect, it } from "vitest";
import { mismatch } from "./retainers";

describe("mismatch", () => {
  it("says nothing when the dots add up", () => {
    expect(mismatch(4, 4)).toBeNull();
    expect(mismatch(0, 0)).toBeNull();
  });
  it("warns of dots not given to a Retainer", () => {
    expect(mismatch(4, 3)).toBe("1 dot of the Retainers background is not given to a Retainer yet.");
    expect(mismatch(4, 1)).toContain("3 dots");
  });
  it("warns of more dots listed than bought", () => {
    expect(mismatch(2, 3)).toBe("The Retainers listed have 1 more dot than the Retainers background.");
  });
});
