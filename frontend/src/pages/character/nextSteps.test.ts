import { describe, expect, it } from "vitest";
import { datesFor } from "../../dates";
import { shown, sinceText, stepText, toneOf, type Step } from "./nextSteps";

const dates = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });
const now = new Date("2026-11-02T12:00:00Z");

const step = (s: Partial<Step>): Step => ({ kind: "finish_creation", who: "player", label: "Finish character creation", link: "/characters/a/create", since: null, at: null, ...s });

describe("stepText", () => {
  it("gives the day and time a downtime is due, or says it is overdue", () => {
    expect(stepText(step({ kind: "downtime_due", label: "Downtime due", at: "2026-11-08T04:59:00Z" }), dates, now)).toBe("Downtime due Sat 7 Nov, 11:59 pm");
    expect(stepText(step({ kind: "downtime_due", label: "Downtime due", at: "2026-11-01T04:59:00Z" }), dates, now)).toBe("Downtime overdue");
  });

  it("says when the next game starts and free changes end", () => {
    expect(stepText(step({ kind: "next_game", who: "coming", label: "Next game", at: "2026-11-15T00:00:00Z" }), dates, now)).toBe("Next game Sat 14 Nov, 7 pm EST");
    expect(stepText(step({ kind: "free_changes", who: "coming", label: "Free changes", at: "2026-12-02T17:00:00Z" }), dates, now)).toBe("Free changes until Wed 2 Dec");
    // By games, the server's words say how many are left.
    expect(stepText(step({ kind: "free_changes", who: "coming", label: "Free changes for 2 more games" }), dates, now)).toBe("Free changes for 2 more games");
  });

  it("is the server's words for the rest", () => {
    expect(stepText(step({}), dates, now)).toBe("Finish character creation");
  });
});

describe("sinceText", () => {
  it("says since when a step has waited on staff, and nothing for the player's own", () => {
    const waiting = step({ kind: "approval_home", who: "staff", label: "Asked Ashes to be its home", since: "2026-10-30T15:00:00Z" });
    expect(sinceText(waiting, dates, now)).toBe("since Fri 30 Oct");
    expect(sinceText(step({ kind: "results", label: "New results", since: "2026-10-30T15:00:00Z" }), dates, now)).toBeNull();
  });
});

describe("shown", () => {
  const results = step({ kind: "results", label: "New results", link: "/characters/a/results", since: "2026-11-01T10:00:00Z" });

  it("shows new results until they are seen on this device, as the Results tab counts them", () => {
    expect(shown([results], null, now.getTime())).toEqual([results]);
    expect(shown([results], "2026-11-01T10:00:00Z", now.getTime())).toEqual([]);
    // With no record on this device, results long since delivered are not new.
    expect(shown([{ ...results, since: "2026-08-01T10:00:00Z" }], null, now.getTime())).toEqual([]);
  });

  it("keeps every other step, and is empty before the answer comes", () => {
    expect(shown([step({})], "2026-11-01T10:00:00Z", now.getTime())).toHaveLength(1);
    expect(shown(undefined, null)).toEqual([]);
  });
});

describe("toneOf", () => {
  it("marks a downtime due in red, the player's other steps in gold", () => {
    expect(toneOf(step({ kind: "downtime_due" }))).toBe("text-blood-bright");
    expect(toneOf(step({}))).toBe("text-gold");
    expect(toneOf(step({ who: "staff" }))).toBe("text-parchment");
  });
});
