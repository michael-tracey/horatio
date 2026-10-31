import { describe, expect, it } from "vitest";
import { askedLine } from "./approvals";

const now = Date.parse("2026-10-31T12:00:00Z");

describe("askedLine", () => {
  it("says the clan and age, the player and when", () => {
    expect(askedLine({ clan: "Brujah", age: "Neonate", player_name: "tour-joiner", asked_at: "2026-10-29T12:00:00Z" }, now)).toBe(
      "Brujah neonate · tour-joiner · asked 2 days ago",
    );
  });

  it("leaves out what it doesn't know, and names an NPC as one", () => {
    expect(askedLine({ clan: null, age: "Ghoul", player_name: null, asked_at: null }, now)).toBe("Ghoul · NPC");
  });
});
