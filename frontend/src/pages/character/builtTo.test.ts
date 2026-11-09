import { describe, expect, it } from "vitest";
import { builtTo } from "./builtTo";

const troupes = [{ id: "a", name: "Ashes" }];

describe("builtTo", () => {
  it("names the troupe a character is built for until it has a home troupe", () => {
    expect(builtTo({ home_troupe_id: null, building_troupe_id: "a" }, troupes)).toEqual({ kind: "troupe", troupeId: "a", name: "Ashes" });
    expect(builtTo({ home_troupe_id: "a", building_troupe_id: "a" }, troupes)).toBeNull();
  });

  it("says the book's rules with no troupe chosen", () => {
    expect(builtTo({ home_troupe_id: null, building_troupe_id: null }, troupes)).toEqual({ kind: "book" });
  });

  it("says when the troupe it was built for has closed", () => {
    expect(builtTo({ home_troupe_id: null, building_troupe_id: "gone" }, troupes)).toEqual({ kind: "closed" });
  });
});
