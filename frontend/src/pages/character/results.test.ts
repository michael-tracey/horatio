import { describe, expect, it } from "vitest";
import { resultParts } from "./results";

describe("a delivered result read back into its parts", () => {
  it("puts each response under the action it answers, feeding first", () => {
    const message = [
      "**Downtime results for Agnes (November)**",
      "**Feeding**\n*Your feeding:* The docks, with Herd 2\n*Result:* **Fed well** Nobody saw.\n\n▸ How it was worked out: Herd 2 covers it.",
      "**Investigate**\n*Your action:* Follow the courier.\n\nAsk at the docks too.\n*Result:* He went to the Elysium.",
      "**Influence**\n*Your action:* Lean on the police.\n*Result:* The desk sergeant owes you a favour.",
    ].join("\n\n");
    expect(resultParts(message)).toEqual([
      {
        heading: "Feeding",
        actionLabel: "Your feeding",
        action: "The docks, with Herd 2",
        result: "**Fed well** Nobody saw.\n\n▸ How it was worked out: Herd 2 covers it.",
      },
      { heading: "Investigate", actionLabel: "Your action", action: "Follow the courier.\n\nAsk at the docks too.", result: "He went to the Elysium." },
      { heading: "Influence", actionLabel: "Your action", action: "Lean on the police.", result: "The desk sergeant owes you a favour." },
    ]);
  });

  it("reads an update, and an answer with a bold line of its own, the same way", () => {
    const message = "**Updated downtime results for Agnes (November)**\n\n**Investigate**\n*Your action:* Look.\n\n**Carefully**\n*Result:* Found it.";
    expect(resultParts(message)).toEqual([{ heading: "Investigate", actionLabel: "Your action", action: "Look.\n\n**Carefully**", result: "Found it." }]);
  });

  it("leaves a message in any other shape to be shown as it is", () => {
    expect(resultParts("Your results: you fed well.")).toBeNull();
    expect(resultParts("**Downtime results for Agnes (November)**")).toBeNull();
  });
});
