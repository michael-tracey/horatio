import { describe, expect, it } from "vitest";
import { auditCounts, auditWho, lineStatus, weight } from "./boonAudits";

describe("boon audits", () => {
  it("heads an audit with what they owe and are owed, and what it weighs", () => {
    expect(auditCounts({ owes_count: 2, owed_count: 0, owes_weight: 4, owed_weight: 0 })).toBe("owes 2 (weighing 4) · is owed 0");
    expect(auditCounts({ owes_count: 1, owed_count: 3, owes_weight: 0.5, owed_weight: 3.25 })).toBe(
      "owes 1 (weighing 0.5) · is owed 3 (weighing 3.25)",
    );
    expect(weight(1.333)).toBe("1.33");
  });

  it("says how a settled boon was settled, and never why someone left beyond what the court knows", () => {
    const line = { other: "Bram", kind: "minor", made_on: "2026-10-03", reason: "", conditions: "" } as const;
    expect(lineStatus({ ...line, status: "settled", settled_how: "called_in" })).toBe("Settled (called in)");
    expect(lineStatus({ ...line, status: "departed" })).toBe("Departed");
    expect(auditWho({ standing: "gone", clan: "Toreador", age: "Neonate" })).toBe("No longer with us · Toreador · Neonate");
    expect(auditWho({ standing: "active", clan: null, age: null })).toBe("Active");
  });
});
