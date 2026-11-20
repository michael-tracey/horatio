import { describe, expect, it } from "vitest";
import { awardText, cartText, whenText } from "./xpPlan";

describe("whenText", () => {
  const line = { held: false, in_cart: false, affordable: false, games: null, total: 42 };

  it("says a line is held, in the cart, affordable, or how many games away", () => {
    expect(whenText({ ...line, held: true }, 30)).toBe("Held already");
    expect(whenText({ ...line, held: true, in_cart: true }, 30)).toBe("In the cart");
    expect(whenText({ ...line, affordable: true }, 30)).toBe("Affordable now");
    expect(whenText({ ...line, games: 1 }, 30)).toBe("About 1 game away");
    expect(whenText({ ...line, games: 3 }, 30)).toBe("About 3 games away");
  });

  it("says when the games away count downtime XP", () => {
    expect(whenText({ ...line, games: 3 }, 30, true)).toBe("About 3 games away, counting downtime XP");
  });

  it("says how much XP is short without a usual award to go by, after the cart", () => {
    expect(whenText(line, 30)).toBe("12 XP short");
    expect(whenText(line, 20)).toBe("22 XP short");
  });
});

describe("awardText", () => {
  const award = { per_game: 8, source: "the troupe's session XP", downtime: 0, downtime_source: null };

  it("says what a game brings, and where from", () => {
    expect(awardText(award)).toBe("about 8 XP a game, from the troupe's session XP");
    expect(awardText({ ...award, downtime: 1.5, downtime_source: "6 XP from 2 downtime cycles over 4 games in the last year" })).toBe(
      "about 9.5 XP a game: 8 from the troupe's session XP, and 1.5 from downtimes (6 XP from 2 downtime cycles over 4 games in the last year)",
    );
    expect(awardText({ ...award, per_game: 0, downtime: 2, downtime_source: "the troupe's 2 XP a downtime, counting a cycle a game" })).toBe(
      "about 2 XP a game, from downtimes (the troupe's 2 XP a downtime, counting a cycle a game)",
    );
  });
});

describe("cartText", () => {
  it("says what the cart takes from the XP unspent, or gives back", () => {
    expect(cartText(0)).toBe("");
    expect(cartText(15)).toBe(", 15 of it for the cart");
    expect(cartText(-2)).toBe(", and 2 XP back from the cart");
  });
});
