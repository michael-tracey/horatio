import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "../../api/types";
import { domitorBody, draftMissing, inClanOf, type DomitorDraft } from "./domitor";

const catalogue = {
  traits: [{ category: "clan", name: "Toreador", in_clan: ["Auspex", "Celerity", "Presence"] }],
} as unknown as CatalogueOut;

const vasquez = { character_id: "v1", name: "Vasquez", kind: "pc", clan: "Toreador", in_clan: ["Auspex", "Celerity", "Presence"] };

describe("a domitor drafted", () => {
  it("gives the ghoul a linked vampire's in-clan disciplines", () => {
    expect(inClanOf({ kind: "linked", choice: vasquez }, catalogue)).toEqual(["Auspex", "Celerity", "Presence"]);
  });

  it("gives the ghoul a named domitor's clan's, or the three a Caitiff chose", () => {
    expect(inClanOf({ kind: "named", name: "Lady V", clan: "Toreador", three: ["", "", ""] }, catalogue)).toEqual(["Auspex", "Celerity", "Presence"]);
    expect(inClanOf({ kind: "named", name: "Old Tom", clan: "Caitiff", three: ["Animalism", "", "Fortitude"] }, catalogue)).toEqual(["Animalism", "Fortitude"]);
  });

  it("says what is missing", () => {
    expect(draftMissing({ kind: "linked", choice: null })).toBe("Choose the vampire.");
    expect(draftMissing({ kind: "named", name: " ", clan: "Toreador", three: [] })).toBe("Give the domitor's name.");
    expect(draftMissing({ kind: "named", name: "Old Tom", clan: "", three: [] })).toBe("Choose the domitor's clan.");
    const caitiff: DomitorDraft = { kind: "named", name: "Old Tom", clan: "Caitiff", three: ["Animalism", "Animalism", "Fortitude"] };
    expect(draftMissing(caitiff)).toMatch(/Name the 3 in-clan disciplines/);
    expect(draftMissing({ ...caitiff, three: ["Animalism", "Auspex", "Fortitude"] })).toBeNull();
  });

  it("sends the dots kept, or all of them moved", () => {
    expect(domitorBody({ kind: "linked", choice: vasquez }, "keep", { Auspex: 2 })).toMatchObject({ character_id: "v1", disciplines: "keep", moved: [] });
    expect(domitorBody({ kind: "named", name: " Lady V ", clan: "Toreador", three: [] }, "move", { Auspex: 2, Presence: 0 })).toEqual({
      character_id: null,
      name: "Lady V",
      clan: "Toreador",
      in_clan: [],
      disciplines: "move",
      moved: [{ name: "Auspex", rating: 2, detail: "" }],
    });
  });
});
