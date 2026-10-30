import { describe, expect, it } from "vitest";
import { emptyDraft, guidanceText, meetsNow, optionFrom, optionsFrom, questType, requestStatus, resultText } from "./quests";

describe("quest requirements", () => {
  it("builds a trait with a specialisation, and influence to expend", () => {
    expect(optionFrom({ ...emptyDraft("trait"), name: " Science ", specialization: "Biology" })).toEqual({
      kind: "trait",
      category: "skills",
      name: "Science",
      rating: 1,
      specialization: "Biology",
    });
    expect(optionFrom({ ...emptyDraft("influence"), level: "6", area: "High Society" })).toEqual({
      kind: "influence",
      type: "elite",
      level: 6,
      area: "High Society",
    });
  });

  it("says what is missing, and in which alternative", () => {
    expect(optionFrom(emptyDraft("trait"))).toBe("Name the trait.");
    expect(optionFrom({ ...emptyDraft("pool"), amount: "x" })).toBe("Give the amount as a number.");
    expect(optionsFrom([{ ...emptyDraft("trait"), name: "Medicine", rating: "3" }, emptyDraft("text")])).toBe("Alternative 2: Say what is needed.");
  });

  it("names who meets an alternative now", () => {
    const checks = [
      { name: "Agnes", meets: [true, false] },
      { name: "Bram", meets: [false, null] },
    ];
    expect(meetsNow(checks, 0)).toEqual(["Agnes"]);
    expect(meetsNow(checks, 1)).toEqual([]);
  });
});

describe("quest words", () => {
  it("writes a quest's type as the troupe does", () => {
    expect(questType({ category: "complex", difficulty: 2 })).toBe("Complex 2");
    expect(questType({ category: "simple", difficulty: 4, downtime_only: true })).toBe("Simple 4 (must be completed in downtime)");
  });

  it("gives the book's numbers as a guide", () => {
    expect(guidanceText({ requirements: 4, scenarios: 2 })).toBe("The book gives this 4 requirements and 2 scenarios.");
    expect(guidanceText({ requirements: 1, scenarios: 1 })).toBe("The book gives this 1 requirement and 1 scenario.");
  });

  it("says where a request stands and how a scenario went", () => {
    expect(requestStatus("waiting")).toBe("Waiting");
    expect(requestStatus("working")).toBe("Being worked on");
    expect(resultText({ number: 2, result: "passed" })).toBe("Scenario 2: passed");
  });
});
