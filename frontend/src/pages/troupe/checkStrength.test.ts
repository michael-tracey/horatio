import { describe, expect, it } from "vitest";
import { writtenStrength } from "./checkStrength";

const LABELS: Record<string, string> = { refuse: "Refuse", complete: "Needed to finish", review: "Allow, for our review" };
const label = (s: string) => LABELS[s] ?? s;

describe("writtenStrength", () => {
  it("names one setting", () => {
    expect(writtenStrength({ strength: "refuse", once_finished: null }, label)).toBe("Refuse");
    expect(writtenStrength({ strength: "complete" }, label)).toBe("Needed to finish");
  });

  it("names the setting once creation is finished after the first", () => {
    expect(writtenStrength({ strength: "complete", once_finished: "review" }, label)).toBe(
      "Needed to finish, then allow, for our review",
    );
  });
});
