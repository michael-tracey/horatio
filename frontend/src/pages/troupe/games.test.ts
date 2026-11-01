import { describe, expect, it } from "vitest";
import type { RsvpOut } from "../../api/types";
import { answeredText, byAnswer, countsText, webcal } from "./games";

const person = (name: string, answer: RsvpOut["answer"]): RsvpOut => ({
  person: { id: name, handle: name.toLowerCase(), display_name: name },
  answer,
  characters: [],
});

describe("countsText", () => {
  it("says how many gave each answer, leaving out the ones nobody gave", () => {
    expect(countsText({ coming: 3, maybe: 1, not_coming: 0 })).toBe("3 coming · 1 maybe");
    expect(countsText({ coming: 0, maybe: 0, not_coming: 2 })).toBe("2 not coming");
  });

  it("says so when nobody has answered", () => {
    expect(countsText({ coming: 0, maybe: 0, not_coming: 0 })).toBe("No answers yet");
  });
});

describe("byAnswer", () => {
  it("groups people by answer in the order offered, without empty groups", () => {
    const groups = byAnswer([person("Ana", "not_coming"), person("Bea", "coming"), person("Cy", "coming")]);
    expect(groups.map((g) => [g.label, g.people.map((p) => p.person.display_name)])).toEqual([
      ["Coming", ["Bea", "Cy"]],
      ["Not coming", ["Ana"]],
    ]);
  });
});

describe("webcal", () => {
  it("swaps the scheme so a calendar app opens it to subscribe", () => {
    expect(webcal("https://horatio.example.org/api/calendar/abc.ics")).toBe("webcal://horatio.example.org/api/calendar/abc.ics");
    expect(webcal("http://localhost:5173/api/calendar/abc.ics")).toBe("webcal://localhost:5173/api/calendar/abc.ics");
  });
});

describe("answeredText", () => {
  it("names the answer and the game, or says it was taken back", () => {
    expect(answeredText("maybe", "Sat 12 Jan, 7 pm GMT")).toBe("Maybe: Sat 12 Jan, 7 pm GMT");
    expect(answeredText(null, "Sat 12 Jan, 7 pm GMT")).toBe("Answer taken back");
  });
});
