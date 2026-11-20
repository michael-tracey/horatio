import { describe, expect, it } from "vitest";
import type { CharacterListOut } from "../api/types";
import { standing } from "./characterList";

const character = (c: Partial<CharacterListOut> = {}) =>
  ({
    status: "active",
    creation_complete: true,
    home_troupe_id: null,
    home_troupe_name: null,
    asking_troupe_id: null,
    asking_troupe_name: null,
    building_troupe_id: null,
    building_troupe_name: null,
    downtime_due: null,
    delivered: [],
    ...c,
  }) as CharacterListOut;

const labels = (notes: { label: string }[]) => notes.map((n) => n.label);

describe("standing", () => {
  it("says a character still being made is in creation, and whose rules it is built to", () => {
    expect(standing(character({ creation_complete: false, building_troupe_id: "a", building_troupe_name: "Ashes" }))).toEqual([
      { label: "In creation", tone: "gold" },
      { label: "Built to Ashes's rules", tone: "mist" },
    ]);
    expect(labels(standing(character({ creation_complete: false })))).toEqual(["In creation", "Built to the book's rules"]);
  });

  it("names the troupe it waits for, and its home", () => {
    // Asking the troupe it is built for: "Waiting for" says whose rules.
    expect(labels(standing(character({ asking_troupe_id: "a", asking_troupe_name: "Ashes", building_troupe_id: "a", building_troupe_name: "Ashes" })))).toEqual([
      "Waiting for Ashes",
    ]);
    expect(labels(standing(character({ home_troupe_id: "a", home_troupe_name: "Ashes" })))).toEqual(["Home: Ashes"]);
    // Moving: still at home in one while the other decides.
    expect(labels(standing(character({ home_troupe_id: "a", home_troupe_name: "Ashes", asking_troupe_id: "e", asking_troupe_name: "Embers" })))).toEqual([
      "Home: Ashes",
      "Waiting for Embers",
    ]);
  });

  it("asks for a home troupe once the character is finished, saying whose rules it is built to", () => {
    expect(standing(character())).toEqual([
      { label: "No home troupe yet", tone: "gold" },
      { label: "Built to the book's rules", tone: "mist" },
    ]);
    expect(labels(standing(character({ building_troupe_id: "a", building_troupe_name: "Ashes" })))).toEqual(["No home troupe yet", "Built to Ashes's rules"]);
  });

  it("says retired, whatever else is true", () => {
    expect(labels(standing(character({ status: "retired", home_troupe_name: "Ashes" })))).toEqual(["Retired"]);
  });
});
