import { describe, expect, it } from "vitest";
import { effectChoices } from "./ResponseEffects";

const none = { applied: [], targets: [], indirect_cost: null, recovering: false, halved: false };

describe("effectChoices", () => {
  it("offers an indirect attack only on a general influence action, at its cost", () => {
    expect(effectChoices(none).map((c) => c.kind)).toEqual(["hungry_dead", "crafts", "performance", "overtaxed"]);
    const attack = effectChoices({ ...none, indirect_cost: 2 }).find((c) => c.kind === "indirect_attack");
    expect(attack).toMatchObject({ aimed: true, label: "Indirect influence attack: another character loses 2 actions (p. 512)" });
  });

  it("offers halving the wait only while Resources recover, once", () => {
    expect(effectChoices({ ...none, recovering: true }).map((c) => c.kind)).toContain("recovery");
    expect(effectChoices({ ...none, recovering: true, halved: true }).map((c) => c.kind)).not.toContain("recovery");
  });
});
