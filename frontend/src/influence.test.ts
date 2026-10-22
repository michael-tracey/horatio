import { describe, expect, it } from "vitest";
import type { InfluenceActionOut, InfluenceStandingOut } from "./api/types";
import { chosenAction, offered, reachNote } from "./influence";

const general = (level: number, name: string): InfluenceActionOut => ({
  key: name.toLowerCase().replace(/ /g, "_"),
  name,
  label: `${level}: ${name}`,
  level,
  conflict: false,
});
const attack: InfluenceActionOut = { key: "attack", name: "Attack", label: "Attack", level: null, conflict: true };
const actions = [general(1, "A Friend in Need"), general(2, "Gossip and Insider Trading"), general(3, "Bureaucratic Errors"), attack];
const standing: InfluenceStandingOut = {
  action_kind: "influence_elite",
  type: "elite",
  rating: 1,
  held: ["News Media"],
  options: ["Finance", "News Media"],
  actions,
};
const labels = (found: InfluenceActionOut[]) => found.map((a) => a.label);

describe("influence actions on the downtime form", () => {
  it("offers general actions up to the rating, and conflict actions always", () => {
    expect(labels(offered(standing, ""))).toEqual(["1: A Friend in Need", "Attack"]);
    expect(labels(offered(standing, "Finance"))).toEqual(["1: A Friend in Need", "Attack"]);
  });

  it("counts the rating one higher with one of the character's own specialisations", () => {
    expect(labels(offered(standing, "News Media"))).toEqual(["1: A Friend in Need", "2: Gossip and Insider Trading", "Attack"]);
  });

  it("says when a specialisation makes the difference", () => {
    expect(reachNote(standing, "News Media", actions[1])).toBe("Your News Media specialisation counts your Elite as 2 for this.");
    expect(reachNote(standing, "News Media", actions[0])).toBeNull();
    expect(reachNote(standing, "", undefined)).toBe("Choose one of your own specialisations to reach a level-2 action.");
    expect(reachNote({ ...standing, held: [] }, "", undefined)).toBeNull();
  });

  it("reads an answer by its key, or an old one by its level", () => {
    expect(chosenAction(actions, { action: "attack" })?.label).toBe("Attack");
    expect(chosenAction(actions, { level: 2 })?.label).toBe("2: Gossip and Insider Trading");
    expect(chosenAction(actions, {})).toBeUndefined();
  });
});
