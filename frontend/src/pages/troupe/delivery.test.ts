import { describe, expect, it } from "vitest";
import { closeFacts, completeFacts, deliveredText, deliveryPlan } from "./delivery";

const downtime = (character_name: string, answered: number, to_answer: number, delivered = false, changed = false) => ({
  character_name,
  answered,
  to_answer,
  delivered,
  changed,
  due: delivered ? changed : answered > 0,
});

describe("what delivering would do", () => {
  const plan = deliveryPlan([
    downtime("Agnes", 3, 3),
    downtime("Bram", 1, 3),
    downtime("Cara", 2, 2, true),
    downtime("Dov", 2, 2, true, true),
    downtime("Esme", 0, 2),
    downtime("Fen", 2, 3, true, true),
  ]);

  it("sends the finished ones with something new, first results or updates", () => {
    expect(plan.ready.map((p) => p.character_name)).toEqual(["Agnes", "Dov"]);
    expect(plan.finished).toBe(3);
  });

  it("holds back the partly written, delivered before or not", () => {
    expect(plan.partial.map((p) => p.character_name)).toEqual(["Bram", "Fen"]);
  });

  it("leaves the unchanged and the ones with nothing written yet", () => {
    expect(plan.current.map((p) => p.character_name)).toEqual(["Cara"]);
    expect(plan.unwritten.map((p) => p.character_name)).toEqual(["Esme"]);
  });
});

describe("what was delivered, in words", () => {
  it("says how many, and how many were updates", () => {
    expect(deliveredText(0, 0)).toBe("Nothing new to deliver.");
    expect(deliveredText(1, 0)).toBe("Delivered 1 downtime.");
    expect(deliveredText(1, 1)).toBe("Delivered 1 downtime, as an update.");
    expect(deliveredText(3, 1)).toBe("Delivered 3 downtimes, 1 of them an update.");
    expect(deliveredText(3, 2)).toBe("Delivered 3 downtimes, 2 of them updates.");
  });
});

describe("closing submissions", () => {
  it("warns before the due date, with who hasn't submitted and the grace period", () => {
    expect(closeFacts({ participants: 1, submitted: 0, due: "Sat 7 Nov", lateUntil: "Mon 9 Nov", isPast: false })).toEqual([
      "It isn't due until Sat 7 Nov.",
      "1 of 1 participant hasn't submitted.",
      "Late downtimes are taken until Mon 9 Nov.",
      "Once closed, nobody can submit, and the cycle can't be opened again.",
    ]);
  });

  it("leaves out the grace period once everyone has submitted", () => {
    expect(closeFacts({ participants: 3, submitted: 3, due: "Sat 7 Nov", lateUntil: "Mon 9 Nov", isPast: true }).slice(0, 2)).toEqual([
      "It was due Sat 7 Nov.",
      "All 3 participants have submitted.",
    ]);
  });
});

describe("marking a cycle complete", () => {
  it("says what is unwritten and undelivered", () => {
    expect(completeFacts({ unwritten: 2, responses: 9, undelivered: 1 })).toEqual([
      "2 of 9 responses aren't written.",
      "1 downtime has results not yet delivered.",
      "Once complete, responses and feeding answers can't be written or changed.",
    ]);
    expect(completeFacts({ unwritten: 0, responses: 9, undelivered: 0 }).slice(0, 2)).toEqual([
      "Every response is written.",
      "Players have every result as it stands.",
    ]);
  });
});
