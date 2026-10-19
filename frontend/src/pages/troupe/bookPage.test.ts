import { describe, expect, it } from "vitest";
import { pageText } from "./bookPage";

describe("pageText", () => {
  it("prefixes a core book page", () => {
    expect(pageText("225")).toBe("p. 225");
  });

  it("leaves a supplement reference as written", () => {
    expect(pageText("Vol. 2, p. 98")).toBe("Vol. 2, p. 98");
  });
});
