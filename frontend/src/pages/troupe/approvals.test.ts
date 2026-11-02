import { describe, expect, it } from "vitest";
import { askedLine, teachingText } from "./approvals";

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

describe("teachingText", () => {
  const teaching = { teacher: "Rook", in_troupe: true, actions: 0, willpower: 1, games: 2, status: "asked" };

  it("says the teacher's player has yet to confirm the Willpower", () => {
    expect(teachingText(teaching)).toBe(
      "Taught by Rook. Their player has not yet confirmed spending 1 Willpower (back after 2 games); it can be approved once they have.",
    );
  });

  it("says when it was spent, refused, or a named NPC with a downtime action", () => {
    expect(teachingText({ ...teaching, status: "spent" })).toBe("Taught by Rook, who spent 1 Willpower (back after 2 games).");
    expect(teachingText({ ...teaching, status: "refused" })).toContain("Rook's player said no");
    expect(teachingText({ teacher: "Old Mother Grey", in_troupe: false, actions: 1, willpower: 0, games: 0, status: "not_needed" })).toBe(
      "Taught by Old Mother Grey, an NPC named by the player. Learning takes 1 downtime action, owed when approved.",
    );
  });
});
