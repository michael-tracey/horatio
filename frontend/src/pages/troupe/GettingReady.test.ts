import { describe, expect, it } from "vitest";
import type { GettingReadyOut } from "../../api/types";
import { readyLines } from "./GettingReady";

const fresh: GettingReadyOut = {
  hidden: false,
  steps: (["profile", "features", "joining", "starting", "house_rules", "staff", "first_game", "players"] as const).map((step) => ({ step, done: false })),
};

describe("getting a troupe ready (#1049)", () => {
  it("keeps the server's order, each step linked to where it is done", () => {
    const lines = readyLines(fresh, "/troupes/t");
    expect(lines.map((l) => [l.label, l.to])).toEqual([
      ["Profile", "/troupes/t#profile"],
      ["Features", "/troupes/t/settings"],
      ["Who may join", "/troupes/t/settings/joining"],
      ["Starting points and XP", "/troupes/t/settings/xp"],
      ["House rules", "/troupes/t/house-rules/checks"],
      ["Staff", "/troupes/t/staff"],
      ["First game", "/troupes/t#profile"],
      ["Invite players", "/troupes/t/players"],
    ]);
    expect(lines.every((l) => !l.done)).toBe(true);
  });

  it("says what is left while a step is to do, and what was done once it is", () => {
    const staffDone = { ...fresh, steps: fresh.steps.map((s) => (s.step === "staff" ? { ...s, done: true } : s)) };
    const staff = (ready: GettingReadyOut) => readyLines(ready, "").find((l) => l.step === "staff")!;
    const [before, after] = [staff(fresh), staff(staffDone)];
    expect(before.text).toMatch(/^Only the lead storyteller so far/);
    expect(after).toMatchObject({ done: true, text: "Others share the work with the lead storyteller." });
  });
});
