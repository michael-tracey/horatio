import { describe, expect, it } from "vitest";
import { actionCost, aimedAt, counterOf, projectOf, withCounter, withProject, withTargets } from "./aim";

const targets = [
  { id: "basil", name: "Basil", cost: 1 },
  { id: "corvin", name: "Corvin", cost: 2 },
];

describe("aiming an action", () => {
  it("keeps the other fields and leaves out what is empty", () => {
    const fields = withTargets({ action: "a_friend_in_need" }, ["basil"]);
    expect(fields).toEqual({ action: "a_friend_in_need", aimed_at: ["basil"] });
    expect(aimedAt(fields)).toEqual(["basil"]);
    expect(withTargets(fields, [])).toEqual({ action: "a_friend_in_need" });
    expect(withProject(withProject(fields, "p1"), "")).toEqual(fields);
    expect(projectOf(withProject(fields, "p1"))).toBe("p1");
  });

  it("drops a Cancel or Observe unless it is aimed at one character", () => {
    const observing = withCounter(withTargets(undefined, ["basil"]), "observe");
    expect(counterOf(observing)).toBe("observe");
    expect(counterOf(withTargets(observing, ["basil", "corvin"]))).toBeNull();
    expect(counterOf(withTargets(observing, ["corvin"]))).toBe("observe");
    expect(counterOf({ counter: "steal" })).toBeNull();
  });

  it("costs two at someone whose Haven doubles it, unless staff say it isn't against them", () => {
    expect(actionCost(undefined, targets)).toBe(1);
    expect(actionCost({ aimed_at: ["basil"] }, targets)).toBe(1);
    expect(actionCost({ aimed_at: ["basil", "corvin"] }, targets)).toBe(2);
    expect(actionCost({ aimed_at: ["corvin"] }, targets, true)).toBe(1);
  });
});
