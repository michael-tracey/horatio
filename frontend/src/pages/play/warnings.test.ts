import { describe, expect, it } from "vitest";
import { derangementWarning } from "./warnings";

describe("derangementWarning", () => {
  it("says nothing until one trait short of the edge", () => {
    expect(derangementWarning(0, 3, 0)).toBeNull();
    expect(derangementWarning(1, 3, 1)).toBeNull();
  });

  it("warns at 2 what a third brings", () => {
    const warning = derangementWarning(2, 3, 0)!;
    expect(warning.level).toBe("near");
    expect(warning.title).toBe("One trait from the edge");
    expect(warning.source).toBe("MET: VtM core, p. 267");
  });

  it("at 3, says how a psychotic break plays out and what it clears, 1 for a Malkavian", () => {
    const warning = derangementWarning(3, 3, 0)!;
    expect(warning.level).toBe("at");
    expect(warning.title).toBe("On the edge of a psychotic break");
    expect(warning.lines.join(" ")).toContain("five minutes");
    expect(warning.lines.join(" ")).toContain("cleared, to 0");
    expect(derangementWarning(3, 3, 1)!.lines.join(" ")).toContain("to 1, as a Malkavian always keeps 1");
  });
});
