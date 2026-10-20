import { describe, expect, it } from "vitest";
import { clanColour, initials } from "./avatar";

describe("placeholder pictures", () => {
  it("show the character's initials", () => {
    expect(initials("Agnes Moreau")).toBe("AM");
    expect(initials("Agnes")).toBe("A");
    expect(initials("Lord Byron the Third")).toBe("LT");
    expect(initials("  émile  zola ")).toBe("ÉZ");
    expect(initials("“Doc” Holliday")).toBe("DH");
    expect(initials("")).toBe("?");
  });

  it("on the clan's colour, a bloodline taking its clan's", () => {
    expect(clanColour("Brujah: True Brujah")).toBe(clanColour("Brujah"));
    expect(clanColour("Toreador")).not.toBe(clanColour("Ventrue"));
    expect(clanColour("Some Homebrew Clan")).toBe(clanColour("Some Homebrew Clan"));
    expect(clanColour(null)).toBe("#2c2531");
  });
});
