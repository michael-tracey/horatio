import { describe, expect, it } from "vitest";
import { backstoryStatus } from "./backstoryStatus";

const standing = (b: Partial<Parameters<typeof backstoryStatus>[0]> = {}) => ({
  write: true,
  review: false,
  written: true,
  troupe_name: "Ashes",
  required: false,
  state: "none" as const,
  approved: false,
  changed_since_approval: false,
  ...b,
});
const reader = { write: false, review: true };

describe("backstoryStatus", () => {
  it("tells the player there is nothing to do while the storytellers have it", () => {
    expect(backstoryStatus(standing(), "", false)).toEqual({
      badge: "Waiting",
      tone: "gold",
      words: "Waiting for Ashes's storytellers to approve it. Nothing for you to do yet.",
    });
    expect(backstoryStatus(standing({ state: "resubmitted" }), "", false)?.words).toBe("Revised and back with Ashes's storytellers. Nothing for you to do yet.");
    expect(backstoryStatus(standing({ changed_since_approval: true }), "", false)?.words).toMatch(/nothing for you to do yet/);
  });

  it("says when the player needs to act", () => {
    const returned = backstoryStatus(standing({ state: "returned" }), "", false)!;
    expect(returned.tone).toBe("blood");
    expect(returned.words).toBe("Ashes's storytellers asked for changes: see their feedback below, revise it, then resubmit it.");
    // A troupe that needs it approved holds a joining character back until it is written.
    const unwritten = backstoryStatus(standing({ written: false, required: true }), "", true)!;
    expect(unwritten.tone).toBe("blood");
    expect(unwritten.words).toBe("Ashes needs it approved before accepting the character. Write it so its storytellers can read it.");
    // Once accepted, it no longer holds anything back.
    expect(backstoryStatus(standing({ written: false, required: true }), "", false)?.tone).toBe("gold");
  });

  it("says who approved it, and that nothing is left to do", () => {
    expect(backstoryStatus(standing({ approved: true, state: "approved" }), " (Morgan, 31 Oct 2026)", false)?.words).toBe(
      "Approved by Ashes (Morgan, 31 Oct 2026). Nothing for you to do.",
    );
  });

  it("tells the storytellers what is theirs to do", () => {
    expect(backstoryStatus(standing(reader), "", false)).toEqual({
      badge: "To read",
      tone: "blood",
      words: "Not yet approved. Read it, then approve it or send it back with feedback.",
    });
    expect(backstoryStatus(standing({ ...reader, state: "returned" }), "", false)?.words).toBe("Sent back to the player with feedback. Waiting for them to revise it.");
    expect(backstoryStatus(standing({ ...reader, approved: true, state: "approved" }), "", false)?.words).toBe("Approved by Ashes.");
  });

  it("says no troupe reads it yet, to its player only", () => {
    expect(backstoryStatus(standing({ troupe_name: null }), "", false)?.badge).toBe("No troupe yet");
    expect(backstoryStatus(standing({ ...reader, troupe_name: null }), "", false)).toBeNull();
  });
});
