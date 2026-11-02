import { describe, expect, it } from "vitest";
import { bookSummary, wordingLabel, wordingOf } from "./houseWording";

describe("house wording", () => {
  it("is there only with text", () => {
    expect(wordingOf(null)).toBeNull();
    expect(wordingOf({ wording: "  ", wording_mode: "added" })).toBeNull();
    expect(wordingOf({ wording: " One target. ", wording_mode: "replaces" })).toEqual({ wording: "One target.", wording_mode: "replaces" });
  });

  it("hides the book's summary only when it replaces it", () => {
    expect(bookSummary("The book's line.", { wording: "Ours.", wording_mode: "added" })).toBe("The book's line.");
    expect(bookSummary("The book's line.", { wording: "Ours.", wording_mode: "replaces" })).toBeNull();
    expect(bookSummary("The book's line.", { wording: "", wording_mode: "replaces" })).toBe("The book's line.");
  });

  it("is always marked as the troupe's", () => {
    expect(wordingLabel({ wording: "Ours.", wording_mode: "added" })).toBe("House rule");
    expect(wordingLabel({ wording: "Ours.", wording_mode: "replaces" })).toBe("House rule, in place of the book's");
  });
});
