import { describe, expect, it } from "vitest";
import { chaseSummary, cycleLine, nameList, notSubmitted, playersToRemind, standing, timeLeft, workLine } from "./cycles";

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
  const day = (at: string) => at.slice(0, 10);

  it("counts whole days to the close, and says when the grace period ends", () => {
    expect(timeLeft("2026-11-07T18:00:00Z", "2026-11-09T18:00:00Z", day, now)).toBe("7 days left · grace to 2026-11-09");
    expect(timeLeft("2026-11-01T18:00:00Z", "2026-11-01T18:00:00Z", day, now)).toBe("1 day left");
    expect(timeLeft("2026-10-31T18:00:00Z", "2026-11-02T18:00:00Z", day, now)).toBe("Less than a day left · grace to 2026-11-02");
  });

  it("says when it is overdue, and when even late ones are no longer taken", () => {
    expect(timeLeft("2026-10-30T18:00:00Z", "2026-11-02T18:00:00Z", day, now)).toBe("Overdue · late downtimes taken until 2026-11-02");
    expect(timeLeft("2026-10-20T18:00:00Z", "2026-10-25T18:00:00Z", day, now)).toBe("The grace period is over");
  });
});

describe("the lines in the lists of cycles", () => {
  const day = (at: string) => at.slice(0, 10);
  const cycle = { closes_at: "2026-11-07T18:00:00Z", participants: 8, submitted: 3, responses: 20, written: 5 };

  it("says when a cycle is due and how far it has got", () => {
    expect(cycleLine({ ...cycle, status: "draft" }, day)).toBe("Due 2026-11-07 · not open yet");
    expect(cycleLine({ ...cycle, status: "open" }, day)).toBe("Due 2026-11-07 · 3 of 8 submitted");
    expect(cycleLine({ ...cycle, status: "closed" }, day)).toBe("3 submitted · 5 of 20 responses written");
    expect(cycleLine({ ...cycle, status: "complete", responses: 1, written: 1 }, day)).toBe("3 submitted · 1 of 1 response written");
  });

  it("says what is left to write", () => {
    expect(workLine({ to_write: 3, open_to_narrators: 2 })).toBe("3 for you to write · 2 open to narrators");
    expect(workLine({ to_write: 0, open_to_narrators: 1 })).toBe("1 open to narrators");
    expect(workLine({})).toBe("Nothing for you to write");
  });
});
