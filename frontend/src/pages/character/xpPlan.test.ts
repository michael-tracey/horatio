import { describe, expect, it } from "vitest";
import { whenText } from "./xpPlan";

describe("whenText", () => {
  const line = { held: false, affordable: false, games: null, total: 42 };

  it("says a line is held, affordable, or how many games away", () => {
    expect(whenText({ ...line, held: true }, 30)).toBe("Held already");
    expect(whenText({ ...line, affordable: true }, 30)).toBe("Affordable now");
    expect(whenText({ ...line, games: 1 }, 30)).toBe("About 1 game away");
    expect(whenText({ ...line, games: 3 }, 30)).toBe("About 3 games away");
  });

  it("says how much XP is short without a usual award to go by", () => {
    expect(whenText(line, 30)).toBe("12 XP short");
  });
});
