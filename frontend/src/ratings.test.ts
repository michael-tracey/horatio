import { describe, expect, it } from "vitest";
import { pipGroups, pipsOf, printedRatings } from "./ratings";

describe("pipGroups", () => {
  it("fills the rating and leaves the rest of five empty", () => {
    expect(pipGroups(3)).toEqual([["held", "held", "held", "empty", "empty"]]);
    expect(pipGroups(0)).toEqual([["empty", "empty", "empty", "empty", "empty"]]);
  });

  it("groups pips in fives, as attributes' ten are on the paper sheet", () => {
    const groups = pipGroups(7, 10);
    expect(groups).toHaveLength(2);
    expect(groups[0]).toEqual(["held", "held", "held", "held", "held"]);
    expect(groups[1]).toEqual(["held", "held", "empty", "empty", "empty"]);
  });

  it("shows a rating past its usual top in full", () => {
    expect(pipGroups(6).flat()).toEqual(["held", "held", "held", "held", "held", "held"]);
    expect(pipGroups(6).map((g) => g.length)).toEqual([5, 1]);
  });

  it("marks the pips still awaiting approval", () => {
    expect(pipGroups(4, 5, 2)).toEqual([["held", "held", "waiting", "waiting", "empty"]]);
    // Nothing waits when the rating has not gone past where approval began.
    expect(pipGroups(2, 5, 2)).toEqual([["held", "held", "empty", "empty", "empty"]]);
  });

  it("marks the pips a change in the cart would add or take away", () => {
    expect(pipGroups(2, 5, null, 4)).toEqual([["held", "held", "planned", "planned", "empty"]]);
    expect(pipGroups(3, 5, null, 2)).toEqual([["held", "held", "planned", "empty", "empty"]]);
    expect(pipGroups(4, 5, null, 6).map((g) => g.length)).toEqual([5, 1]);
    // No change, nothing planned.
    expect(pipGroups(2, 5, null, 2)).toEqual(pipGroups(2));
  });
});

describe("pipsOf", () => {
  it("gives attributes ten pips and everything else five", () => {
    expect(pipsOf("attributes")).toBe(10);
    expect(pipsOf("skills")).toBe(5);
  });
});

describe("printedRatings", () => {
  it("follows the setting unless the print asks for one or the other", () => {
    expect(printedRatings(null, "pips")).toBe("pips");
    expect(printedRatings("numbers", "pips")).toBe("numbers");
    expect(printedRatings("pips", "numbers")).toBe("pips");
    expect(printedRatings("sideways", "numbers")).toBe("numbers");
  });
});
