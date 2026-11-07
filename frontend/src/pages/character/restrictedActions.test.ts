import { describe, expect, it } from "vitest";
import { restrictedText } from "./DowntimeTab";

const line = (source: string, only = "", action_kind = "general") => ({ action_kind, source, amount: 1, note: "", only });

describe("restrictedText", () => {
  it("names each Science action and its field on the questions of its kind", () => {
    const lines = [line("Everyone"), line("Science: Chemistry", "Chemistry"), line("Computer"), line("Science: Physics", "Physics")];
    expect(restrictedText(lines, "general")).toEqual(["1 Science action (Chemistry only)", "1 Science action (Physics only)"]);
    expect(restrictedText(lines, "resources")).toEqual([]);
  });
});
