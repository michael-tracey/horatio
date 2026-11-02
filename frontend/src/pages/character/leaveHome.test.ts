import { describe, expect, it } from "vitest";
import { withdrawnText } from "./leaveHome";

describe("a request withdrawn on leaving the home troupe", () => {
  it("says the XP that comes back", () => {
    expect(withdrawnText({ what: "Celerity 1 → 2", refund: 6 })).toBe("Celerity 1 → 2 (6 XP back)");
  });

  it("says nothing of XP when none was held", () => {
    expect(withdrawnText({ what: "Diablerie", refund: 0 })).toBe("Diablerie");
    expect(withdrawnText({ what: "Remove Rugged", refund: 0 })).toBe("Remove Rugged");
  });

  it("says a free change undone takes its refund back", () => {
    expect(withdrawnText({ what: "Brawl 3 → 1 as a free change", refund: -4 })).toBe(
      "Brawl 3 → 1 as a free change (the 4 XP it refunded is taken back)",
    );
  });
});
