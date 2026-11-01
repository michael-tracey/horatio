import { describe, expect, it } from "vitest";
import { feedingChangeText } from "./FeedingSetting";

describe("feedingChangeText", () => {
  it("says what switching feeding off or on keeps", () => {
    expect(feedingChangeText({ feeding: "book", resonance: true }, { feeding: "off", resonance: true })).toBe(
      "Feeding isn't tracked now. What was recorded is kept, for if you switch it back on.",
    );
    expect(feedingChangeText({ feeding: "off", resonance: false }, { feeding: "book", resonance: false })).toBe("Feeding is tracked again, with what was recorded before.");
  });

  it("names an optional rule switched on or off", () => {
    expect(feedingChangeText({ feeding: "book", resonance: false }, { feeding: "book", resonance: true })).toBe("Blood Resonance is on.");
    expect(feedingChangeText({ feeding: "book", resonance: true }, { feeding: "book", resonance: false })).toBe("Blood Resonance is off.");
  });
});
