import { describe, expect, it } from "vitest";
import type { LookupOut } from "./api/types";
import { datesFor } from "./dates";
import { lookupTexts, ownEntryLabel, resultText } from "./influenceLookups";

const dates = datesFor({
  time_zone: "Europe/London",
  date_format: "day_month",
  clock: "12",
});
const lookup: LookupOut = {
  type: "underworld",
  action_name: "Word on the Street",
  strength: 2,
  window: {
    since: "2026-04-03T22:59:00Z",
    until: "2026-07-02T22:59:00Z",
    days: 90,
  },
  specializations: ["Criminal Organizations", "Finance", "Transportation"],
  found: [
    {
      short_id: "UW259",
      happened_at: "2026-05-14T18:00:00Z",
      specialization: "Finance",
      action: "3: Illegal Favors",
      purpose: "To get a ledger out of the bank",
      times: 1,
    },
    {
      short_id: "UW268",
      happened_at: "2026-07-11T19:30:00Z",
      specialization: "Transportation",
      action: "5: Lockdown",
      purpose: "To secure the location of May's gather",
      times: 3,
    },
  ],
  answers: [
    {
      response_id: "a",
      question: "Underworld influence action",
      answer: "Ask around",
      body: "",
      status: "assigned",
    },
    {
      response_id: "b",
      question: "Underworld influence action",
      answer: "Ask again",
      body: "",
      status: "assigned",
    },
  ],
};

describe("filling a lookup from the influence log", () => {
  it("lists what it found oldest first, with full dates and ids, never who", () => {
    expect(resultText(lookup, dates)).toBe(
      [
        "Word on the Street, strength 2, in Criminal Organizations, Finance and Transportation, since 3 Apr 2026:",
        "- 14 May 2026, Finance, 3: Illegal Favors, To get a ledger out of the bank (UW259)",
        "- 11 Jul 2026, Transportation, 5: Lockdown, To secure the location of May's gather (this action is logged 3 times) (UW268)",
      ].join("\n"),
    );
  });

  it("writes dates in the reader's format", () => {
    const us = datesFor({
      time_zone: "America/New_York",
      date_format: "month_day",
      clock: "12",
    });
    expect(resultText(lookup, us)).toContain("since 4/3/2026:");
    expect(resultText(lookup, us)).toContain("- 5/14/2026, Finance");
  });

  it("says when nothing is found, and the window it searched", () => {
    expect(resultText({ ...lookup, found: [] }, dates)).toBe(
      "Word on the Street, strength 2, in Criminal Organizations, Finance and Transportation: nothing found since 3 Apr 2026.",
    );
    expect(resultText({ ...lookup, specializations: [], found: [] }, dates)).toBe(
      "Word on the Street covers your Underworld specialisations, and you have none, so it finds nothing.",
    );
  });

  it("puts the result on the last answer and combines the others with it", () => {
    const texts = lookupTexts(lookup, dates);
    expect(texts.a).toBe("Combined with your other Word on the Street actions: strength 2, results below.");
    expect(texts.b).toMatch(/^Word on the Street, strength 2/);
  });
});

describe("picking an entry to block", () => {
  it("says what the entry was, and its id", () => {
    const entry = { ...lookup.found[1]!, id: "x", type: "underworld" as const };
    expect(ownEntryLabel(entry, dates)).toBe("UW268 · 11 Jul 2026 · Underworld, Transportation · 5: Lockdown · To secure the location of May's gather");
  });
});
