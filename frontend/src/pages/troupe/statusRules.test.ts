import { describe, expect, it } from "vitest";
import type { StatusSourceOut } from "../../api/types";
import { givenByText } from "./statusRules";

const source = (s: Partial<StatusSourceOut> & Pick<StatusSourceOut, "kind" | "name">): StatusSourceOut => ({
  page: null,
  aliases: [],
  condition: "",
  house: false,
  ...s,
});

describe("givenByText", () => {
  it("names each title, social age and merit that gives the status", () => {
    expect(
      givenByText([
        source({ kind: "title", name: "Harpy", aliases: ["Master Harpy"] }),
        source({ kind: "title", name: "Keeper of Elysium" }),
        source({ kind: "social_age", name: "Elder" }),
        source({ kind: "merit", name: "Prestigious Sire" }),
      ]),
    ).toBe("Given here by the titles Harpy (or Master Harpy) and Keeper of Elysium; the social age Elder; the merit Prestigious Sire.");
  });

  it("says when a title gives it only sometimes, and which titles are the troupe's own", () => {
    expect(
      givenByText([
        source({ kind: "title", name: "Prince" }),
        source({ kind: "title", name: "Petty Prince" }),
        source({ kind: "title", name: "Seneschal", condition: "while the Prince is absent" }),
        source({ kind: "title", name: "Master of Revels", house: true }),
      ]),
    ).toBe("Given here by the titles Prince, Petty Prince, Seneschal (while the Prince is absent) and Master of Revels (ours).");
  });

  it("says nothing when nothing gives it", () => {
    expect(givenByText([])).toBeNull();
  });
});
