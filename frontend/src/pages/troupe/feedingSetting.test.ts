import { describe, expect, it } from "vitest";
import { feedingChangeText } from "./FeedingSetting";

describe("feedingChangeText", () => {
  it("says what switching feeding off or on keeps", () => {
    expect(feedingChangeText({ feeding: "book", resonance: true, territories: false, rack: false }, { feeding: "off", resonance: true, territories: false, rack: false })).toBe(
      "Feeding isn't tracked now. What was recorded is kept, for if you switch it back on.",
    );
    expect(feedingChangeText({ feeding: "off", resonance: false, territories: false, rack: false }, { feeding: "book", resonance: false, territories: false, rack: false })).toBe("Feeding is tracked again, with what was recorded before.");
  });

  it("names an optional rule switched on or off, and the Rack going with Blood Resonance", () => {
    const all = { feeding: "book" as const, resonance: true, territories: true, rack: true };
    expect(feedingChangeText(all, { ...all, resonance: false, rack: false })).toBe("Blood Resonance: off. The Rack (advanced feeding): off.");
    expect(feedingChangeText({ ...all, territories: false }, all)).toBe("Feeding territories: on.");
    expect(feedingChangeText({ feeding: "book", resonance: false, territories: false, rack: false }, { feeding: "book", resonance: true, territories: false, rack: false })).toBe("Blood Resonance: on.");
    expect(feedingChangeText({ feeding: "book", resonance: true, territories: false, rack: false }, { feeding: "book", resonance: false, territories: false, rack: false })).toBe("Blood Resonance: off.");
  });
});
