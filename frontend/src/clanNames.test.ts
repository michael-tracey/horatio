import { describe, expect, it } from "vitest";
import { clanNamed, withClanNames } from "./clanNames";

describe("clanNamed", () => {
  it.each([
    ["Assamite", "Banu Haqim"],
    ["Assamite: Sorcerer", "Banu Haqim: Sorcerer"],
    ["Assamite: Vizier", "Banu Haqim: Vizier"],
    ["Assamite: Diluted Blood", "Banu Haqim: Diluted Blood"],
    ["Assamite: Unbroken", "Banu Haqim: Unbroken"],
    ["Thaumaturgy: Kiss of the Asp (Assamite)", "Thaumaturgy: Kiss of the Asp (Banu Haqim)"],
    ["Shakari's Shroud (Assamite)", "Shakari's Shroud (Banu Haqim)"],
    ["Assamite antitribu", "Banu Haqim antitribu"],
    ["Follow the Path of Blood: the Assamite creed.", "Follow the Path of Blood: the Banu Haqim creed."],
    ["The Assamites keep to the shadows.", "The Banu Haqim keep to the shadows."],
    ["Drinking non-Assamite vampire blood", "Drinking non-Banu Haqim vampire blood"],
    ["an Assamite Vizier's ghoul", "a Banu Haqim Vizier's ghoul"],
    ["An Assamite hunts. So does an Assamite.", "A Banu Haqim hunts. So does a Banu Haqim."],
    ["Brujah", "Brujah"],
    ["Assamitesque", "Assamitesque"],
  ])("reads %j as %j under Banu Haqim", (stored, shown) => {
    expect(clanNamed(stored, "Banu Haqim")).toBe(shown);
  });

  it("leaves the stored name for a troupe calling the clan Assamite", () => {
    expect(clanNamed("Assamite: Vizier", "Assamite")).toBe("Assamite: Vizier");
    expect(clanNamed("the Assamites", "Assamite")).toBe("the Assamites");
  });
});

describe("withClanNames", () => {
  it("lets either name find the clan", () => {
    const found = withClanNames("Assamite: Vizier").toLowerCase();
    expect(found).toContain("assamite");
    expect(found).toContain("banu haqim");
    expect(withClanNames("Brujah")).toBe("Brujah");
  });
});
