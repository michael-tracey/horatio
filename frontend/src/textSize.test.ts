import { describe, expect, it } from "vitest";
import { rootFontSize } from "./textSize";

describe("rootFontSize", () => {
  it("leaves normal text at the browser's size", () => {
    expect(rootFontSize("normal", "/characters")).toBeNull();
  });

  it("makes large text bigger everywhere on screen, the Play View included", () => {
    expect(rootFontSize("large", "/characters")).toBe("115%");
    expect(rootFontSize("large", "/play/characters/abc")).toBe("115%");
  });

  it("keeps printed sheets and badges at their own sizes", () => {
    expect(rootFontSize("large", "/print/characters/abc")).toBeNull();
    expect(rootFontSize("large", "/print/troupes/abc/badges")).toBeNull();
  });
});
