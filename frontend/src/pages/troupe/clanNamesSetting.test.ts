import { describe, expect, it } from "vitest";
import { clanNamesChangeText } from "./ClanNamesSetting";

describe("clanNamesChangeText", () => {
  it("says what the clan is called now, in the plural each name takes", () => {
    expect(clanNamesChangeText("Banu Haqim")).toBe("The clan is called the Banu Haqim here now.");
    expect(clanNamesChangeText("Assamite")).toBe("The clan is called the Assamites here now.");
  });
});
