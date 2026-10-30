import { describe, expect, it } from "vitest";
import { clanMeritWhy, clanMeritsLine, clanPoints, comesWithClan } from "./clanMerits";

const coyote = { name: "Bloodline: Coyote", points: 2, why: "Gangrel: Coyote is a bloodline.", page: "238", detail: "" };
const rare = { name: "Rare Clan", points: 4, why: "Lasombra is rare in the Camarilla setting.", page: "403-404", detail: "" };

describe("clan merits", () => {
  it("never offers a bloodline merit as a pick, and the rarity merits once the setting gives them", () => {
    expect(comesWithClan("Bloodline: Noiad", { rarity_known: false })).toBe(true);
    expect(comesWithClan("Rare Clan", { rarity_known: false })).toBe(false);
    expect(comesWithClan("Rare Clan", { rarity_known: true })).toBe(true);
    expect(comesWithClan("Code of Honor", { rarity_known: true })).toBe(false);
  });

  it("adds up and words what the clan takes", () => {
    expect(clanPoints({ clan_merits: [coyote, rare] })).toBe(6);
    expect(clanMeritsLine({ clan_merits: [] })).toBeNull();
    expect(clanMeritsLine({ clan_merits: [coyote] })).toBe("The clan takes Bloodline: Coyote (2 points) from your merit points.");
    expect(clanMeritsLine({ clan_merits: [rare, coyote] })).toBe(
      "The clan takes Rare Clan (4 points) and Bloodline: Coyote (2 points) from your merit points.",
    );
  });

  it("says why, with the page", () => {
    expect(clanMeritWhy(coyote)).toBe("Gangrel: Coyote is a bloodline. (p. 238)");
    expect(clanMeritWhy({ why: "Your troupe plays Tremere as rare.", page: null })).toBe("Your troupe plays Tremere as rare.");
  });
});
