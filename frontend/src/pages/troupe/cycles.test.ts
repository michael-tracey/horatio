import { describe, expect, it } from "vitest";
import { datesFor } from "../../dates";
import { chaseSummary, cycleLine, nameList, notSubmitted, pastDue, playersToRemind, standing, timeLeft, workLine } from "./cycles";

const taking = (character_name: string, player_id: string, submission_status: string | null, removed = false) => ({
  character_name,
  player_id,
  submission_status,
  removed,
});

describe("chasing submissions", () => {
  const participants = [
    taking("Agnes", "p1", "draft"),
    taking("Bram", "p1", null),
    taking("Cara", "p2", null),
    taking("Dov", "p3", "submitted"),
    taking("Esme", "p4", null, true),
  ];

  it("says where each downtime stands", () => {
    expect(participants.map(standing)).toEqual(["started", "not started", "not started", "submitted", "removed"]);
  });

  it("sums them up, leaving out what there is none of", () => {
    expect(chaseSummary(participants)).toBe("1 submitted · 1 started · 2 not started · 1 removed");
    expect(chaseSummary([taking("Dov", "p3", "submitted")])).toBe("1 submitted");
    expect(chaseSummary([])).toBe("No one is taking part.");
  });

  it("reminds each player once, however many of their characters are waiting, and never a removed one", () => {
    expect(notSubmitted(participants).map((p) => p.character_name)).toEqual(["Agnes", "Bram", "Cara"]);
    expect(playersToRemind(participants)).toBe(2);
  });

  it("names a few, and counts the rest", () => {
    expect(nameList(["Agnes"])).toBe("Agnes");
    expect(nameList(["Agnes", "Bram", "Cara"])).toBe("Agnes, Bram and Cara");
    expect(nameList(["A", "B", "C", "D", "E", "F", "G"], 5)).toBe("A, B, C, D and 3 others");
  });
});

describe("how long is left", () => {
  const now = new Date("2026-10-31T12:00:00Z");
  const due = (at: string) => datesFor({ time_zone: "UTC", date_format: "day_month", clock: "24" }).due(at, now);

  it("counts whole days to Due, and says until when late ones are accepted, with the time", () => {
    expect(timeLeft("2026-11-07T18:00:00Z", "2026-11-09T18:00:00Z", due, now)).toBe("7 days left · accepted until Mon 9 Nov, 18:00");
    expect(timeLeft("2026-11-01T18:00:00Z", "2026-11-01T18:00:00Z", due, now)).toBe("1 day left");
    expect(timeLeft("2026-10-31T18:00:00Z", "2026-11-02T18:30:00Z", due, now)).toBe("Less than a day left · accepted until Mon 2 Nov, 18:30");
  });

  it("says when it is past Due, and when even late ones are no longer taken", () => {
    expect(timeLeft("2026-10-30T18:00:00Z", "2026-11-02T18:00:00Z", due, now)).toBe("Past Due · accepted until Mon 2 Nov, 18:00");
    expect(timeLeft("2026-10-20T18:00:00Z", "2026-10-25T18:00:00Z", due, now)).toBe("The grace period is over");
  });
});

describe("past Due", () => {
  const cycle = { closes_at: "2026-11-07T18:00:00Z" };

  it("is past Due from the moment Due comes, not before", () => {
    expect(pastDue(cycle, new Date("2026-11-07T17:59:59Z"))).toBe(false);
    expect(pastDue(cycle, new Date("2026-11-07T18:00:00Z"))).toBe(true);
    expect(pastDue(cycle, new Date("2026-11-20T00:00:00Z"))).toBe(true);
  });
});

describe("the lines in the lists of cycles", () => {
  const now = new Date("2026-10-31T12:00:00Z");
  const due = (at: string) => datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" }).due(at, now);
  const cycle = { closes_at: "2026-11-07T23:00:00Z", participants: 8, submitted: 3, responses: 20, written: 5 };

  it("says when a cycle is due, with its time, and how far it has got", () => {
    expect(cycleLine({ ...cycle, status: "draft" }, due)).toBe("Due Sat 7 Nov, 6:00 pm · not open yet");
    expect(cycleLine({ ...cycle, status: "open" }, due)).toBe("Due Sat 7 Nov, 6:00 pm · 3 of 8 submitted");
    expect(cycleLine({ ...cycle, status: "closed" }, due)).toBe("3 submitted · 5 of 20 responses written");
    expect(cycleLine({ ...cycle, status: "complete", responses: 1, written: 1 }, due)).toBe("3 submitted · 1 of 1 response written");
  });

  it("says what is left to write", () => {
    expect(workLine({ to_write: 3, open_to_narrators: 2 })).toBe("3 for you to write · 2 open to narrators");
    expect(workLine({ to_write: 0, open_to_narrators: 1 })).toBe("1 open to narrators");
    expect(workLine({})).toBe("Nothing for you to write");
  });
});
