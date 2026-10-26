import { afterEach, describe, expect, it } from "vitest";
import { added, askException, costText, describe as describeLine, loadCart, ordered, pick, plannedRating, setRating, swap, toChange, unpick, type CartLine } from "./cart";

const brawl = { category: "skills", name: "Brawl", detail: "", rating: 2 };

describe("setRating", () => {
  it("puts a raise in the cart from the saved rating, and steps it on", () => {
    let lines = setRating([], brawl, 3);
    expect(lines).toEqual([{ kind: "set", category: "skills", name: "Brawl", detail: "", from: 2, to: 3 }]);
    lines = setRating(lines, brawl, 4);
    expect(lines).toHaveLength(1);
    expect(describeLine(lines[0]!)).toBe("Brawl 2 → 4");
    expect(plannedRating(lines, brawl)).toBe(4);
  });

  it("takes a change out of the cart when it goes back to where it was saved", () => {
    const lines = setRating(setRating([], brawl, 3), brawl, 2);
    expect(lines).toEqual([]);
    expect(plannedRating(lines, brawl)).toBeNull();
  });

  it("lowers below the saved rating as a change of its own", () => {
    expect(describeLine(setRating([], brawl, 1)[0]!)).toBe("Brawl 2 → 1");
  });

  it("reads new traits and removals plainly", () => {
    const dominate = { category: "disciplines", name: "Dominate", detail: "", rating: 0 };
    expect(describeLine(setRating([], dominate, 1)[0]!)).toBe("Add Dominate 1");
    expect(describeLine(setRating([], { ...dominate, fixed: true }, 2)[0]!)).toBe("Add Dominate");
    expect(describeLine(setRating([], brawl, 0)[0]!)).toBe("Remove Brawl");
    expect(added(setRating([], dominate, 1), [brawl])).toHaveLength(1);
    expect(added(setRating([], brawl, 3), [brawl])).toHaveLength(0);
  });
});

describe("swap, pick and unpick", () => {
  it("replaces a swap of the same trait", () => {
    const lines = swap(swap([], "focus_physicals", "Strength", "Dexterity"), "focus_physicals", "Strength", "Stamina");
    expect(lines).toEqual([{ kind: "swap", category: "focus_physicals", from_name: "Strength", to_name: "Stamina" }]);
    expect(swap(lines, "focus_physicals", "Strength", "Strength")).toEqual([]);
  });

  it("takes a pick only in the cart back out of it", () => {
    const trait = { category: "skills", name: "Brawl", detail: "" };
    expect(unpick(pick([], trait, 4), trait)).toEqual([]);
    expect(unpick([], trait)).toEqual([{ kind: "unpick", ...trait }]);
    expect(unpick(unpick([], trait), trait)).toHaveLength(1);
  });
});

describe("ordered", () => {
  it("takes back picks and lowers ratings first, then the rest as added", () => {
    const raise = setRating([], brawl, 3)[0]!;
    const lower = setRating([], { ...brawl, name: "Dodge" }, 1)[0]!;
    const back: CartLine = { kind: "unpick", category: "skills", name: "Melee", detail: "" };
    const add: CartLine = { kind: "pick", category: "skills", name: "Stealth", detail: "", rating: 3 };
    expect(ordered([raise, add, lower, back])).toEqual([back, lower, raise, add]);
  });
});

describe("toChange", () => {
  it("sends a rating with the one it was made from", () => {
    expect(toChange(setRating([], brawl, 3)[0]!)).toEqual({ kind: "set", category: "skills", name: "Brawl", detail: "", rating: 3, from_rating: 2, teacher: "", picks: [] });
  });

  it("sends the free traits chosen with a merit, and shows them", () => {
    const royalty = { category: "merits", name: "Ventrue Royalty", detail: "", rating: 0, fixed: true };
    const picks = [{ grant: "merits/Ventrue Royalty/1", name: "Resources", detail: "", amount: 4 }];
    const lines = setRating([], { ...royalty, picks, picked: "Resources 4" }, 2);
    expect(toChange(lines[0]!)).toMatchObject({ kind: "set", name: "Ventrue Royalty", picks });
    expect(describeLine(lines[0]!)).toBe("Add Ventrue Royalty (free: Resources 4)");
  });

  it("sends a line asked as an exception with why, and whether free", () => {
    const exception = { reason: "A plot reward", free: true };
    expect(toChange(setRating([], { ...brawl, exception }, 3)[0]!)).toMatchObject({ rating: 3, exception });
  });
});

describe("askException", () => {
  it("asks staff for one line of the cart, kept as it is raised further", () => {
    const lines = setRating([], brawl, 3);
    const exception = { reason: "Taught by the Prince", free: false };
    const asked = askException(lines, lines[0]!, exception);
    expect(asked[0]).toMatchObject({ kind: "set", to: 3, exception });
    expect(setRating(asked, brawl, 4)[0]).toMatchObject({ to: 4, exception });
    // Lowered back below where it was saved, it is no longer asked.
    expect(setRating(asked, brawl, 1)[0]).not.toHaveProperty("exception");
  });
});

describe("costText", () => {
  it("says what is spent or given back", () => {
    expect(costText(4)).toBe("4 XP");
    expect(costText(-2)).toBe("2 XP back");
    expect(costText(0)).toBe("");
    expect(costText(null)).toBe("");
  });
});

describe("loadCart", () => {
  afterEach(() => localStorage.clear());

  it("is empty when nothing, or nothing sensible, is kept", () => {
    expect(loadCart("a")).toEqual([]);
    localStorage.setItem("horatio.cart.a", "not json");
    expect(loadCart("a")).toEqual([]);
    localStorage.setItem("horatio.cart.a", JSON.stringify([{ kind: "nonsense" }, { kind: "swap", category: "c", from_name: "x", to_name: "y" }]));
    expect(loadCart("a")).toEqual([{ kind: "swap", category: "c", from_name: "x", to_name: "y" }]);
  });
});
