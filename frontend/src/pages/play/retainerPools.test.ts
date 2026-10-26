import { describe, expect, it } from "vitest";
import { poolLine } from "./retainerPools";

describe("a Retainer's pools", () => {
  it("are twice its dots, and 5 more in each specialty", () => {
    expect(poolLine({ pool: 8, specialties: ["Brawl", "Stealth"] })).toBe("Pool 8 · Brawl 13, Stealth 13");
    expect(poolLine({ pool: 2, specialties: [] })).toBe("Pool 2");
  });
});
