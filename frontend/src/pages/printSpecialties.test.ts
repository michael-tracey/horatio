import { describe, expect, it } from "vitest";
import { bracketed, fitsInline, specialtiesByParent, specialtyName } from "./printSpecialties";

const trait = (category: string, name: string, detail = "", specializes: { category: string; name: string } | null = null, pending_from: number | null = null) => ({
  category,
  name,
  detail,
  specializes,
  pending_from,
});
const LORE = { category: "skills", name: "Lore" };
const CONTACTS = { category: "backgrounds", name: "Contacts" };

describe("specialtyName", () => {
  it("is the catalogue name, or the text of a Custom one", () => {
    expect(specialtyName(trait("lore_specializations", "Kindred"))).toBe("Kindred");
    expect(specialtyName(trait("contacts_specializations", "Custom", "Police"))).toBe("Police");
  });
});

describe("specialtiesByParent", () => {
  it("groups specialisations under the trait they specialise, in order", () => {
    const traits = [
      trait("skills", "Lore"),
      trait("backgrounds", "Contacts"),
      trait("lore_specializations", "Kindred", "", LORE),
      trait("contacts_specializations", "Custom", "Police", CONTACTS),
      trait("lore_specializations", "Sabbat", "", LORE),
    ];
    const { of, orphans } = specialtiesByParent(traits);
    expect(of(traits[0]!)).toEqual(["Kindred", "Sabbat"]);
    expect(of(traits[1]!)).toEqual(["Police"]);
    expect(of(trait("skills", "Brawl"))).toEqual([]);
    expect(orphans).toEqual([]);
  });

  it("marks one awaiting approval", () => {
    const traits = [trait("skills", "Linguistics"), trait("linguistics_specializations", "Latin", "", { category: "skills", name: "Linguistics" }, 0)];
    expect(specialtiesByParent(traits).of(traits[0]!)).toEqual(["Latin awaiting approval"]);
  });

  it("leaves over those whose parent is not on the sheet", () => {
    const kindred = trait("lore_specializations", "Kindred", "", LORE);
    expect(specialtiesByParent([trait("skills", "Brawl"), kindred]).orphans).toEqual([kindred]);
  });
});

describe("bracketed", () => {
  it("lists names in brackets, or nothing", () => {
    expect(bracketed(["French", "Latin"])).toBe("(French, Latin)");
    expect(bracketed([])).toBe("");
  });
});

describe("fitsInline", () => {
  it("keeps short lists on the trait's line and moves long ones under it", () => {
    expect(fitsInline("Academics", "(History)")).toBe(true);
    expect(fitsInline("Contacts", "(Police, Press)")).toBe(true);
    expect(fitsInline("Linguistics", "(French, Latin)")).toBe(false);
    expect(fitsInline("Lore", "(Kindred, Sabbat, Lupines)")).toBe(false);
  });
});
