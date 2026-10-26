import { describe, expect, it } from "vitest";
import type { FreeChoicesOut } from "../../api/types";
import { fill, place, placed, pointsUsed, rule, sayable, setDetail, summary, toggle, toSend } from "./freeChoices";

const offer = (extra: Partial<FreeChoicesOut>): FreeChoicesOut => ({
  grant: "merits/Ventrue Royalty/1",
  category: "backgrounds",
  category_name: "Backgrounds",
  options: ["Allies", "Contacts", "Herd", "Resources"].map((name) => ({ name, rating: null, needs_detail: false })),
  places: null,
  count: null,
  points: null,
  picks: [],
  complete: false,
  locked: null,
  ...extra,
});

const ROYALTY = offer({ places: [4, 3, 2] });

describe("placing dots", () => {
  it("puts an amount on a trait, and moves a trait that was placed elsewhere", () => {
    let picks = place([], ROYALTY, 4, "Resources");
    picks = place(picks, ROYALTY, 3, "Herd");
    expect(picks.map((p) => [p.name, p.amount])).toEqual([
      ["Resources", 4],
      ["Herd", 3],
    ]);
    picks = place(picks, ROYALTY, 3, "Resources");
    expect(picks.map((p) => [p.name, p.amount])).toEqual([["Resources", 3]]);
    expect(placed(picks, ROYALTY, 4)).toBeUndefined();
  });

  it("changes the trait an amount is on, and empties it", () => {
    let picks = place([], ROYALTY, 4, "Resources");
    picks = place(picks, ROYALTY, 4, "Contacts");
    expect(picks.map((p) => p.name)).toEqual(["Contacts"]);
    expect(place(picks, ROYALTY, 4, "")).toEqual([]);
  });

  it("says what is asked", () => {
    expect(rule(ROYALTY)).toBe("Place 4, 3 and 2 dots, each in a different one.");
    expect(rule(offer({ count: 1 }))).toBe("Choose one.");
    expect(rule(offer({ count: 2 }))).toBe("Choose 2.");
    expect(rule(offer({ points: 3 }))).toBe("Up to 3 points of merits.");
  });
});

describe("choosing a few", () => {
  const two = offer({ grant: "g", count: 2 });

  it("fills slots in order and empties one", () => {
    let picks = fill([], two, 0, "Anarch");
    picks = fill(picks, two, 1, "Custom", "Latin");
    expect(picks.map((p) => [p.name, p.detail])).toEqual([
      ["Anarch", ""],
      ["Custom", "Latin"],
    ]);
    picks = fill(picks, two, 0, "");
    expect(picks.map((p) => p.name)).toEqual(["Custom"]);
  });

  it("keeps other grants' picks", () => {
    const other = offer({ grant: "h", count: 2 });
    const picks = fill(fill([], two, 0, "Anarch"), other, 0, "Brujah");
    expect(fill(picks, two, 0, "").map((p) => p.grant)).toEqual(["h"]);
  });

  it("needs words for a pick that asks for them", () => {
    const custom = offer({ grant: "g", count: 2, options: [{ name: "Custom", rating: null, needs_detail: true }] });
    const picks = fill([], custom, 0, "Custom");
    expect(sayable(picks, [custom])).toBe(false);
    expect(sayable(setDetail(picks, custom, "Custom", "", "Latin"), [custom])).toBe(true);
    expect(toSend([{ grant: "g", name: "Custom", detail: " Latin ", amount: 0 }])[0]?.detail).toBe("Latin");
  });
});

describe("a budget of points", () => {
  const sabbat = offer({
    grant: "s",
    category: "merits",
    category_name: "Merits",
    points: 3,
    options: [
      { name: "Executioner", rating: 1, needs_detail: false },
      { name: "Fanatic", rating: 2, needs_detail: false },
    ],
  });

  it("adds up what is picked and lets one go", () => {
    let picks = toggle([], sabbat, "Executioner", true);
    picks = toggle(picks, sabbat, "Fanatic", true);
    expect(pointsUsed(picks, sabbat)).toBe(3);
    expect(pointsUsed(toggle(picks, sabbat, "Fanatic", false), sabbat)).toBe(1);
  });
});

describe("the cart's words", () => {
  it("lists the picks", () => {
    const picks = place(place([], ROYALTY, 4, "Resources"), ROYALTY, 3, "Herd");
    expect(summary([ROYALTY], picks)).toBe("Resources 4, Herd 3");
  });
});
