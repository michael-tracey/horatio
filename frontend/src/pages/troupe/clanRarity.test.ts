import { describe, expect, it } from "vitest";
import { bookRarity } from "./ClanRarity";

describe("bookRarity", () => {
  const tremere = { clan: "Tremere", book: { Anarch: "rare", Camarilla: "common", Sabbat: "uncommon" }, house: null };
  const lhiannan = { clan: "Lhiannan", book: { Anarch: "rare", Camarilla: "rare", Sabbat: "rare" }, house: null };

  it("gives the setting's rarity when the troupe has one sect", () => {
    expect(bookRarity(tremere, "Sabbat")).toBe("uncommon");
    expect(bookRarity({ ...tremere, book: {} }, "Camarilla")).toBe("restricted");
  });

  it("gives each sect's otherwise, once where they agree", () => {
    expect(bookRarity(tremere, null)).toBe("rare (Anarch), common (Camarilla), uncommon (Sabbat)");
    expect(bookRarity(lhiannan, null)).toBe("rare");
  });
});
