import { describe, expect, it } from "vitest";
import { isSrdPage, pageText } from "./bookPage";

describe("pageText", () => {
  it("prefixes a core book page", () => {
    expect(pageText("225")).toBe("p. 225");
  });

  it("leaves a supplement reference as written", () => {
    expect(pageText("Vol. 2, p. 98")).toBe("Vol. 2, p. 98");
  });

  it("names the SRD for a link to one of its pages", () => {
    const page = "https://www.oneworldofdarkness.com/srd-v20/rituals/vile-swarm";
    expect(isSrdPage(page)).toBe(true);
    expect(pageText(page)).toBe("V20 LARP SRD");
    expect(isSrdPage("Vol. 2, p. 98")).toBe(false);
  });
});
