import { describe, expect, it } from "vitest";
import type { HavenAdvantageChoiceOut } from "../../api/types";
import { canChoose, countText, havenCount, havenDots } from "./haven";

const advantage = (name: string, over: Partial<HavenAdvantageChoiceOut> = {}): HavenAdvantageChoiceOut => ({
  name,
  page: "102",
  text: "",
  needs: "",
  allowed: true,
  free_with: "",
  free: false,
  ...over,
});

const list = [advantage("Library"), advantage("Luxury"), advantage("Size"), advantage("Security", { free_with: "Security", free: true }), advantage("Occult", { needs: "Occult", allowed: false })];

describe("a Haven's advantages", () => {
  it("counts Security free for someone with the skill", () => {
    expect(havenCount(["Library", "Security"], list)).toEqual({ used: 1, free: ["Security"] });
    expect(countText(["Library", "Luxury", "Security"], list, 2)).toBe("2 of 2 dots used, plus Security free");
    expect(countText([], list, 1)).toBe("0 of 1 dot used");
  });

  it("stops at the dots, but still offers what is free or already ticked", () => {
    const chosen = ["Library", "Luxury"];
    expect(canChoose("Size", chosen, list, 2)).toBe(false);
    expect(canChoose("Security", chosen, list, 2)).toBe(true);
    expect(canChoose("Luxury", chosen, list, 2)).toBe(true);
    expect(canChoose("Size", ["Library"], list, 2)).toBe(true);
  });

  it("needs the skill an advantage asks for", () => {
    expect(canChoose("Occult", [], list, 3)).toBe(false);
  });
});

describe("havenDots", () => {
  const row = (category: string, name: string, rating: number | null) => ({ category, name, rating }) as never;
  it("counts every dot of Haven on the sheet, and nothing else", () => {
    expect(havenDots({ traits: [row("backgrounds", "Haven", 2), row("backgrounds", "Herd", 3), row("skills", "Security", 1)] })).toBe(2);
    expect(havenDots({ traits: [row("backgrounds", "Resources", 3)] })).toBe(0);
    expect(havenDots({ traits: [row("backgrounds", "Haven", null)] })).toBe(0);
  });
});
