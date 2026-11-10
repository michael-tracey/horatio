import { describe, expect, it } from "vitest";
import { orphanedKinds, orphanedText, type Kind } from "./Specializations";

const kind = (category: string, parent_name: string, held: Kind["held"]): Kind => ({
  category,
  name: category === "linguistics_specializations" ? "Languages" : "Lore Specialisations",
  parent_category: "skills",
  parent_name,
  parent_rating: 0,
  options: [],
  from_troupe: false,
  custom: true,
  held,
  allowed: 0,
  counted: held.length,
});

describe("specialisations held without their skill", () => {
  const languages = kind("linguistics_specializations", "Linguistics", [{ name: "Custom", detail: "Spanish" }]);
  const lore = kind("lore_specializations", "Lore", []);

  it("are the kinds held with no rating in the skill they specialise", () => {
    expect(orphanedKinds([languages, lore], [])).toEqual([languages]);
    expect(orphanedKinds([languages], [{ category: "skills", name: "Linguistics", rating: 0 }])).toEqual([languages]);
    expect(orphanedKinds([languages], [{ category: "skills", name: "Linguistics", rating: 1 }])).toEqual([]);
  });

  it("say what to do, and that a native tongue needs no Linguistics", () => {
    expect(orphanedText(languages)).toBe(
      "Take Linguistics to keep them, or remove them. A native tongue needs no Linguistics and isn't listed here.",
    );
    expect(orphanedText(lore)).toBe("Take Lore to keep them, or remove them.");
  });
});
