import { describe, expect, it } from "vitest";
import { apologyFor, claimsText, disgracedText } from "./boonStatus";

describe("status and boons (#694)", () => {
  it("says a Disgraced creditor's boon need not be repaid", () => {
    expect(disgracedText("Bram")).toBe("Need not be repaid while Bram is Disgraced (p. 316).");
  });

  it("puts a slip right with a minor boon under Warned and a major one under Disgraced", () => {
    expect(apologyFor("Warned")).toEqual({ kind: "minor", words: "a minor boon" });
    expect(apologyFor("Disgraced")).toEqual({ kind: "major", words: "a major boon" });
    expect(apologyFor("Praised")).toBeUndefined();
  });

  it("names who spending Praised can claim from", () => {
    expect(claimsText(["Cosima", "Vidal", "Wren"], "Camarilla", "Court of Ash")).toBe("Not in your debt: Cosima, Vidal and Wren.");
    expect(claimsText([], "Camarilla", "Court of Ash")).toBe("Everyone of the Camarilla in Court of Ash is already in your debt.");
    expect(claimsText([], null, "Court of Ash")).toBe("Only a character a sect has Accepted can claim help with Praised.");
  });
});
