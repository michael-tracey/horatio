import { describe, expect, it } from "vitest";
import { actionText, entryText, sharersText, totalText } from "./sharedBackgrounds";

describe("shared backgrounds", () => {
  it("says what each entry did", () => {
    expect(actionText({ kind: "contribution", dots: 2 })).toBe("put in 2 dots");
    expect(actionText({ kind: "withdrawal", dots: 1 })).toBe("took out 1 dot");
    expect(entryText({ kind: "use", dots: null, name: "Agnes" })).toBe("Agnes drew on it");
  });

  it("shows the total, and what is put in beyond the most", () => {
    expect(totalText({ total: 3, put_in: 3, most: 5 })).toBe("3 of 5 dots");
    expect(totalText({ total: 5, put_in: 7, most: 5 })).toBe("5 of 5 dots, from 7 put in");
  });

  it("names who shares it and who has taken their dots out", () => {
    expect(
      sharersText([
        { name: "Agnes", dots: 2 },
        { name: "Bram", dots: 1 },
        { name: "Cora", dots: 0 },
      ]),
    ).toBe("Sharing it: Agnes 2 dots, Bram 1 dot. Took their dots out: Cora.");
    expect(sharersText([{ name: "Cora", dots: 0 }])).toBe("No one has dots in it now. Took their dots out: Cora.");
  });
});
