import { describe, expect, it } from "vitest";
import type { CatalogueOut } from "./api/types";
import { houseLabels } from "./houseTraits";

describe("houseLabels", () => {
  it("names each house merit or flaw by category and name, and nothing else", () => {
    const catalogue = {
      traits: [
        { category: "merits", name: "Acute Sense", house: null },
        { category: "merits", name: "Lucky Star", house: { label: "House merit of Night Court" } },
      ],
    } as unknown as CatalogueOut;
    expect([...houseLabels(catalogue)]).toEqual([["merits/Lucky Star", "House merit of Night Court"]]);
    expect(houseLabels(undefined).size).toBe(0);
  });
});
