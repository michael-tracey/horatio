import { describe, expect, it } from "vitest";
import { retainerName, retainerSource } from "./retainers";

describe("a Retainer in a list", () => {
  it("is named, or says it has no name yet", () => {
    expect(retainerName({ name: "Bocephus" })).toBe("Bocephus");
    expect(retainerName({ name: "" })).toBe("A Retainer not yet named");
  });
  it("says where its dots come from when they are not bought on the sheet", () => {
    expect(retainerSource({ bought: true, from_merit: "" })).toBeNull();
    expect(retainerSource({ bought: false, from_merit: "Ghostly Retainer" })).toBe("from Ghostly Retainer");
    expect(retainerSource({ bought: false, from_merit: "" })).toBe("listed before each Retainer was bought on its own");
  });
});
