import { describe, expect, it } from "vitest";
import type { LeavingWarningsOut } from "../../api/types";
import { leavingWarnings } from "./leavingWarnings";

const found = (over: Partial<LeavingWarningsOut> = {}): LeavingWarningsOut => ({ thralls: [], shared: [], staff: true, ...over });
const agnes = { name: "Agnes", troupe: "Lords of the Night" };
const cora = { name: "Cora", troupe: "Lords of the Night" };
const haven = { name: "The coterie's Haven", background: "Haven", troupe: "Lords of the Night", others: ["Cora"] };

describe("leavingWarnings", () => {
  it("warns that listing a dead regnant tells its thrall's player", () => {
    const said = leavingWarnings(found({ thralls: [agnes] }), { name: "Bram", reason: "final_death", listed: true, remembering: false });
    expect(said).toHaveLength(1);
    expect(said[0]).toContain("Bram is the regnant of Agnes.");
    expect(said[0]).toContain("Listing Bram under “No longer with us” tells the thrall's player that Bram died now.");
    expect(said[0]).toContain("(MET: VTM p. 296)");
  });

  it("names remembrances too, and several thralls", () => {
    const said = leavingWarnings(found({ thralls: [agnes, cora] }), { name: "Bram", reason: "final_death", listed: true, remembering: true });
    expect(said[0]).toContain("Bram is the regnant of Agnes and Cora.");
    expect(said[0]).toContain("Listing Bram under “No longer with us” and opening remembrances tells their players");
    expect(said[0]).toContain("Leave them until the bonds have faded");
  });

  it("says nothing of bonds unless it is Final Death and something would tell", () => {
    const thralls = found({ thralls: [agnes] });
    expect(leavingWarnings(thralls, { name: "Bram", reason: "final_death", listed: false, remembering: false })).toEqual([]);
    expect(leavingWarnings(thralls, { name: "Bram", reason: "off_field", listed: true, remembering: false })).toEqual([]);
    expect(leavingWarnings(thralls, { name: "Bram", reason: null, listed: false, remembering: false })).toEqual([]);
  });

  it("tells staff to hold off a shared background's withdrawal, and a player what it shows", () => {
    const leaving = { name: "Bram", reason: "inactive", listed: false, remembering: false };
    expect(leavingWarnings(found({ shared: [haven] }), leaving)).toEqual([
      "Bram has dots in The coterie's Haven with Cora. Logging their withdrawal shows those sharers' players that Bram left: hold off if they shouldn't know yet.",
    ]);
    expect(leavingWarnings(found({ shared: [haven], staff: false }), leaving)[0]).toContain("When the storytellers log their withdrawal");
    expect(leavingWarnings(found({ shared: [haven] }), { ...leaving, reason: null })).toEqual([]);
  });
});
