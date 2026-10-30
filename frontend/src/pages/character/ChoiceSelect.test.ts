import { describe, expect, it } from "vitest";
import { choiceDetail, choiceParts } from "./ChoiceSelect";

const ARTIST = ["Crafts", "Performance"];

describe("choiceParts", () => {
  it("splits a choice of skill from its field (#312)", () => {
    expect(choiceParts("Performance: Singing", ARTIST)).toEqual({ choice: "Performance", field: "Singing" });
    expect(choiceParts("Crafts:Painting", ARTIST)).toEqual({ choice: "Crafts", field: "Painting" });
    expect(choiceParts("Performance", ARTIST)).toEqual({ choice: "Performance", field: "" });
  });

  it("keeps a detail that names no choice whole", () => {
    expect(choiceParts("", ARTIST)).toEqual({ choice: "", field: "" });
    expect(choiceParts("Herd", ["Haven", "Herd", "Resources"])).toEqual({ choice: "Herd", field: "" });
    expect(choiceParts("Singing", ARTIST)).toEqual({ choice: "Singing", field: "" });
  });

  it("keeps the field as typed, a space at its end too", () => {
    expect(choiceParts(choiceDetail("Performance", "Opera "), ARTIST)).toEqual({ choice: "Performance", field: "Opera " });
  });
});

describe("choiceDetail", () => {
  it("joins the choice and its field, or gives the choice alone", () => {
    expect(choiceDetail("Performance", "Singing")).toBe("Performance: Singing");
    expect(choiceDetail("Performance", "  ")).toBe("Performance");
    expect(choiceDetail("Herd", "")).toBe("Herd");
  });
});
