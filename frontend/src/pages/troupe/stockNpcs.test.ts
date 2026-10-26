import { describe, expect, it } from "vitest";
import { allowedPowers, expandPower } from "./stockNpcs";

const disciplines = ["Celerity", "Dominate", "Thaumaturgy: Path of Blood", "Thaumaturgy: Rego Vitae"];

describe("allowedPowers", () => {
  it("keeps to a kind's list", () => {
    const kind = { any_discipline: false, specializations: ["Celerity"], numina: [] };
    expect(allowedPowers(kind, disciplines)).toEqual(["Celerity"]);
  });
  it("lets a Thaumaturgy wildcard take any of its paths", () => {
    const kind = { any_discipline: false, specializations: ["Thaumaturgy: *"], numina: [] };
    expect(allowedPowers(kind, disciplines)).toEqual(["Thaumaturgy: Path of Blood", "Thaumaturgy: Rego Vitae"]);
  });
  it("puts a kind's own numina first, and lets 'any' take every discipline", () => {
    const kind = { any_discipline: true, specializations: [], numina: [{ name: "True Faith", page: 491, levels: [] }] };
    expect(allowedPowers(kind, disciplines)).toEqual(["True Faith", ...disciplines]);
  });
});

describe("expandPower", () => {
  it("says up to its dots", () => expect(expandPower("Celerity", 3)).toBe("Celerity up to 3"));
});
