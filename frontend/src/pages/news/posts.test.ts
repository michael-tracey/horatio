import { describe, expect, it } from "vitest";
import type { PostOut } from "../../api/types";
import { datesFor } from "../../dates";
import { deskSections, discordParts, discordText, excerpt, inkOn, scheduleProblem, suggestedTime } from "./posts";

function post(over: Partial<PostOut>): PostOut {
  return {
    id: "p",
    troupe_id: "t",
    kind: "news",
    status: "draft",
    agency_id: "a",
    title: "Fire at the docks",
    body: "",
    dateline: "",
    picture: null,
    author: "Mara",
    proposed_by: null,
    mine: false,
    note: "",
    publish_at: null,
    published_at: null,
    unread: false,
    byline: "",
    pinned_until: null,
    pinned: false,
    dismissed: false,
    important: false,
    discord: null,
    ...over,
  };
}

describe("scheduling", () => {
  const now = new Date("2026-11-07T18:00:00Z");

  it("needs a date and time to come", () => {
    expect(scheduleProblem("", null, now)).toBe("Choose a date and time.");
    expect(scheduleProblem("2026-11-07T12:00", new Date("2026-11-07T17:00:00Z"), now)).toBe("Choose a time to come, or publish it now.");
    expect(scheduleProblem("2026-11-07T13:01", new Date("2026-11-07T18:01:00Z"), now)).toBeNull();
  });

  it("is entered on the writer's own clock", () => {
    const newYork = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });
    // 7 pm in New York is midnight UTC in November.
    expect(newYork.fromInput("2026-11-07T19:00").toISOString()).toBe("2026-11-08T00:00:00.000Z");
    expect(newYork.inputText("2026-11-07T19:00")).toBe("Sat 7 Nov 2026, 7:00 pm EST");
  });

  it("suggests the next whole hour at least half an hour away", () => {
    const utc = datesFor({ time_zone: "UTC", date_format: "day_month", clock: "24" });
    expect(suggestedTime(new Date("2026-11-07T18:10:00Z"), utc.toInput)).toBe("2026-11-07T19:00");
    expect(suggestedTime(new Date("2026-11-07T18:40:00Z"), utc.toInput)).toBe("2026-11-07T20:00");
  });
});

describe("the desk", () => {
  it("puts proposals first and the soonest scheduled first, leaving out what's published", () => {
    const sections = deskSections([
      post({ id: "d", status: "draft" }),
      post({ id: "late", status: "scheduled", publish_at: "2026-11-09T00:00:00Z" }),
      post({ id: "soon", status: "scheduled", publish_at: "2026-11-08T00:00:00Z" }),
      post({ id: "n", status: "proposed" }),
      post({ id: "out", status: "published" }),
    ]);
    expect(sections.map((s) => [s.title, s.posts.map((p) => p.id)])).toEqual([
      ["Proposed by narrators", ["n"]],
      ["Drafts", ["d"]],
      ["Scheduled", ["soon", "late"]],
    ]);
  });

  it("says where a story stands on Discord", () => {
    expect(discordText(post({ discord: { state: "app_only", reason: "No news channel is chosen.", next_attempt_at: null } }))).toBe("In the app only: No news channel is chosen.");
    expect(discordText(post({ status: "published", discord: { state: "failed", reason: "The Horatio bot cannot see or post in that channel.", next_attempt_at: null } }))).toBe(
      "Not on Discord: The Horatio bot cannot see or post in that channel.",
    );
    expect(discordText(post({ status: "published", discord: { state: "sent", reason: null, next_attempt_at: null } }))).toBe("On Discord.");
    expect(discordText(post({ discord: null }))).toBeNull();
  });
});

describe("reading", () => {
  it("opens a story with its first paragraph as plain words", () => {
    expect(excerpt("# Extra\n\nThe **Prince** was [seen](https://x.org) at the docks.\n\nMore.")).toBe("The Prince was seen at the docks.");
    const long = excerpt(`${"word ".repeat(60)}end`, 40);
    expect(long.length).toBeLessThanOrEqual(41);
    expect(long.endsWith("…")).toBe(true);
  });

  it("writes on a masthead in ink that reads", () => {
    expect(inkOn("#8b1e1e")).toBe("#f4ecd8");
    expect(inkOn("#f0e68c")).toBe("#111111");
  });

  it("splits a long story over embeds between paragraphs, the link at the end", () => {
    const body = Array.from({ length: 6 }, (_, n) => `Paragraph ${n}. ${"w".repeat(1500)}`).join("\n\n");
    const parts = discordParts("Boston", body);
    expect(parts).toHaveLength(3);
    expect(parts[0]!.startsWith("*Boston*\n\nParagraph 0.")).toBe(true);
    expect(parts.every((p) => p.length <= 4000)).toBe(true);
    expect(parts[2]!.endsWith("Read in Horatio")).toBe(true);
    expect(discordParts("", "")).toEqual(["Read in Horatio"]);
  });
});
