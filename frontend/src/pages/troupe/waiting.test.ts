import { describe, expect, it } from "vitest";
import type { WaitingLine } from "../../api/types";
import { dueText, tabCounts, waitingTotal } from "./waiting";

const line = (kind: string, count: number | null): WaitingLine => ({ kind, label: kind, count, link: "/" });

describe("tabCounts", () => {
  it("adds each line to its tab, from the same numbers as Waiting on you", () => {
    const lines = [
      line("cycle_open", null),
      line("approvals", 2),
      line("backstories", 1),
      line("status_to_resolve", 3),
      line("cycle_unassigned", 4),
      line("deliveries", 1),
      line("cycle_unwritten", 9),
      line("my_responses", 2),
      line("quest_requests", 1),
      line("effects_ending", 1),
    ];
    expect(tabCounts(lines)).toEqual({ approvals: 2, characters: 4, downtimes: 5, work: 2, quests: 1, influence: 1 });
    // Responses not yet written are on My work for each person, not counted twice.
    expect(waitingTotal(lines)).toBe(15);
  });

  it("counts nothing before the lines load", () => {
    expect(waitingTotal(undefined)).toBe(0);
  });
});

describe("dueText", () => {
  it("says how many days are left, by the calendar", () => {
    expect(dueText("2026-10-31", "2026-11-07")).toBe("due in 7 days");
    expect(dueText("2026-10-31", "2026-11-01")).toBe("due tomorrow");
    expect(dueText("2026-10-31", "2026-10-31")).toBe("due today");
  });

  it("and how long ago it was due", () => {
    expect(dueText("2026-11-08", "2026-11-07")).toBe("due yesterday");
    expect(dueText("2026-11-10", "2026-11-07")).toBe("due 3 days ago");
  });

  it("counts across a change of clocks", () => {
    expect(dueText("2026-10-30", "2026-11-02")).toBe("due in 3 days");
  });
});
