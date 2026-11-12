import { describe, expect, it } from "vitest";
import type { PlayBoonOut } from "../../api/types";
import { aBoon, playerSettles, reportedText, settledText, standingFirst } from "./boons";

const boon = (over: Partial<PlayBoonOut>): PlayBoonOut => ({
  id: "b1",
  other: "Bram",
  other_id: null,
  kind: "minor",
  made_on: "2026-10-03",
  reason: "",
  conditions: "",
  notify_on_trade: false,
  state: "registered",
  settled_how: null,
  settled_at: null,
  settled_note: "",
  can_settle: false,
  ...over,
});

describe("the Play View's boons", () => {
  it("puts standing boons first and settled ones after, keeping their order", () => {
    const list = [boon({ id: "a", state: "settled" }), boon({ id: "b" }), boon({ id: "c", state: "settled" }), boon({ id: "d" })];
    const { standing, settled } = standingFirst(list);
    expect(standing.map((b) => b.id)).toEqual(["b", "d"]);
    expect(settled.map((b) => b.id)).toEqual(["a", "c"]);
  });

  it("says how and when a boon was settled, with its note", () => {
    const day = (at: string) => `day ${at.slice(0, 10)}`;
    expect(settledText(boon({ settled_how: "called_in", settled_at: "2026-10-16T20:00:00Z", settled_note: "For influence." }), day)).toBe(
      "Settled: called in, day 2026-10-16. For influence.",
    );
    expect(settledText(boon({ settled_how: "forgiven", settled_at: null }), day)).toBe("Settled: forgiven.");
  });

  it("offers a creditor only calling in and forgiving, not formally ignoring", () => {
    expect(playerSettles.map((s) => s.value)).toEqual(["called_in", "forgiven"]);
  });

  it("words a report either way", () => {
    expect(aBoon("major", 1)).toBe("a major boon");
    expect(aBoon("trivial", 3)).toBe("3 trivial boons");
    expect(reportedText("Agnes", "Bram", "owes", "minor", 1, "Elysium")).toBe("Reported to Elysium's ledger: Agnes owes Bram a minor boon.");
    expect(reportedText("Agnes", "The Moon", "owed", "blood", 2, "Elysium")).toBe("Reported to Elysium's ledger: The Moon owes Agnes 2 blood boons.");
  });
});
