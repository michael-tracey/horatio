import { describe, expect, it } from "vitest";
import { moved } from "./settingStyle";

describe("moved", () => {
  const ids = ["a", "b", "c", "d"];

  it("puts an entry in the place of the one it is dropped on, either way", () => {
    expect(moved(ids, "d", 1)).toEqual(["a", "d", "b", "c"]);
    expect(moved(ids, "a", 2)).toEqual(["b", "c", "a", "d"]);
  });

  it("moves one place up or down", () => {
    expect(moved(ids, "c", 1)).toEqual(["a", "c", "b", "d"]);
    expect(moved(ids, "b", 2)).toEqual(["a", "c", "b", "d"]);
  });

  it("keeps within the list", () => {
    expect(moved(ids, "a", -1)).toEqual(ids);
    expect(moved(ids, "d", 9)).toEqual(ids);
  });
});
