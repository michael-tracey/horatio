import { describe, expect, it } from "vitest";
import { initialXpText, rarityTiers, settingText } from "./settingDocument";

describe("the Setting Style Document's generated parts", () => {
  it("names one sect as the setting, several as factions, none as any", () => {
    expect(settingText({ sects: ["Camarilla"], setting: "Camarilla" })).toMatch(/^Camarilla\. Every character/);
    expect(settingText({ sects: ["Anarch", "Camarilla", "Sabbat"], setting: null })).toMatch(/^Factions: Anarch, Camarilla and Sabbat\. Each character/);
    expect(settingText({ sects: ["Anarch", "Camarilla"], setting: null })).toMatch(/^Factions: Anarch and Camarilla\./);
    expect(settingText({ sects: [], setting: null })).toMatch(/^Any sect\./);
  });

  it("lists rarity changes by their rarity here, with restricted only when used", () => {
    const lasombra = { clan: "Lasombra", rarity: "uncommon", book: "rare", note: "due to story" };
    expect(rarityTiers([lasombra]).map((t) => [t.rarity, t.changes.length])).toEqual([
      ["common", 0],
      ["uncommon", 1],
      ["rare", 0],
    ]);
    expect(rarityTiers([{ ...lasombra, rarity: "restricted" }]).map((t) => t.rarity)).toContain("restricted");
  });

  it("gives the initial XP, with the incentive's working when it is on", () => {
    expect(initialXpText({ initial_xp: 100, incentive: null })).toBe("Initial XP is 100 XP.");
    expect(initialXpText({ initial_xp: 80, incentive: { base: 30, earned: 200, bonus: 50, total: 80 } })).toBe(
      "Initial XP is the base award (30 XP) + the New Character Incentive (25% of the 200 XP a character could have earned in the chronicle, 50 XP): 80 XP (p. 349).",
    );
  });
});
