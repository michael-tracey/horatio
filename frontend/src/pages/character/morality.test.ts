import { describe, expect, it } from "vitest";
import type { CatalogueOut, SheetOut, TraitOut } from "../../api/types";
import { heldMorality, moralityLabel, moralityOptions, moveMorality, willpowerAndHealth } from "./morality";

const trait = (category: string, name: string) => ({ category, name }) as unknown as TraitOut;
const catalogue = {
  traits: [
    trait("paths", "Night"),
    trait("paths", "Caine"),
    trait("paths", "Humanity"),
    trait("health_levels", "Healthy"),
    trait("health_levels", "Incapacitated"),
    trait("health_levels", "Injured"),
    trait("willpower_sources", "Willpower"),
    trait("skills", "Brawl"),
  ],
} as unknown as CatalogueOut;
const sheet = (...held: [string, string, number][]) =>
  ({ traits: held.map(([category, name, rating]) => ({ category, name, rating })) }) as unknown as SheetOut;
const names = (traits: TraitOut[]) => traits.map((t) => t.name);

describe("an NPC's Morality", () => {
  it("offers Humanity first, then each Path by name", () => {
    expect(names(moralityOptions(catalogue))).toEqual(["Humanity", "Caine", "Night"]);
    expect(moralityLabel("Humanity")).toBe("Humanity");
    expect(moralityLabel("Caine")).toBe("Path of Caine");
  });

  it("is the one path the sheet follows, at its rating", () => {
    const options = moralityOptions(catalogue);
    expect(heldMorality(sheet(["paths", "Caine", 4], ["skills", "Brawl", 2]), options)).toEqual({ name: "Caine", rating: 4 });
    expect(heldMorality(sheet(["paths", "Humanity", 2], ["paths", "Night", 3]), options)).toEqual({ name: "Night", rating: 3 });
    expect(heldMorality(sheet(), options)).toEqual({ name: "Humanity", rating: 0 });
  });

  it("moves to another path at the same rating", () => {
    expect(moveMorality({ name: "Humanity", rating: 4 }, "Caine")).toEqual({ category: "paths", name: "Caine", rating: 4 });
    expect(moveMorality({ name: "Caine", rating: 4 }, "Caine")).toBeNull();
    // With none held, the choice waits for its first dot.
    expect(moveMorality({ name: "Humanity", rating: 0 }, "Caine")).toBeNull();
  });

  it("is followed by Willpower and the health levels in sheet order", () => {
    expect(names(willpowerAndHealth(catalogue))).toEqual(["Willpower", "Healthy", "Injured", "Incapacitated"]);
  });
});
