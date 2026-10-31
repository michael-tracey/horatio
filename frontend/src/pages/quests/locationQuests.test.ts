import { describe, expect, it } from "vitest";
import { changeFromRequest, effectText, modifiersText, questName, removalText } from "./locationQuests";

describe("location quests", () => {
  it("starts the change from what the player asked", () => {
    expect(changeFromRequest({ kind: "acquire", details: {} })?.kind).toBe("acquire");
    expect(changeFromRequest({ kind: "quality", details: { quality: "Profitable", detail: "" } })).toMatchObject({ kind: "quality", quality: "Profitable" });
    expect(changeFromRequest({ kind: "undermine", details: { negative: "Insolvent" } })).toMatchObject({ kind: "negative", negative: "Insolvent" });
    expect(changeFromRequest({ kind: "undermine", details: { victory: "Steal the ledger" } })).toMatchObject({ kind: "infiltrate", victory: "Steal the ledger" });
    expect(changeFromRequest({ kind: "repair", details: {} })).toBeNull();
  });

  it("names the quest after the change", () => {
    expect(questName(changeFromRequest({ kind: "acquire", details: {} })!, "Ruby's Bar")).toBe("Acquire Ruby's Bar");
    expect(questName(changeFromRequest({ kind: "quality", details: { quality: "Profitable" } })!, "Ruby's Bar")).toBe("Profitable for Ruby's Bar");
  });

  it("says what a quality gives, and that it is off without saying why to a player", () => {
    const profitable = { quality: "Profitable", gives: "Resources 1", on: true, off_because: "" };
    expect(effectText("Ruby's Bar", profitable)).toBe("Resources 1, from Ruby's Bar (Profitable)");
    expect(effectText("Ruby's Bar", { ...profitable, on: false })).toBe("Resources 1, from Ruby's Bar (Profitable): not available this cycle");
    expect(effectText("Ruby's Bar", { ...profitable, on: false, off_because: "Insolvent ×1" })).toBe(
      "Resources 1, from Ruby's Bar (Profitable): not available this cycle, because of Insolvent ×1",
    );
  });

  it("gives the difficulty's reasons and what removes a negative", () => {
    expect(modifiersText([{ reason: "Rating 2" }, { reason: "Historic +1" }])).toBe("Rating 2 · Historic +1");
    expect(removalText("Insolvent", 3)).toBe("Elite 3");
    expect(removalText("Damaged", 2)).toBe("Resources 2");
    expect(removalText("Out of Code", 1)).toBe("Underworld 1");
  });
});
