import { describe, expect, it } from "vitest";
import type { ExpendableOut, OtherOut, SeenOut } from "../../api/types";
import { leadershipOf, matching, sectLine, shownSeen } from "./others";
import type { ShownEntry } from "./tracker";

const seen: SeenOut = {
  key: "held:1",
  name: "Loyal",
  type: "Fleeting",
  spent: false,
  learnable: true,
  known: true,
  learned_by: "tap-1",
  held_id: "1",
  patron: "Prince Varga",
  place: "Elysium",
  story: "For holding the door",
  ending: null,
  removable: false,
};

function entry(id: string, undone: boolean): ShownEntry {
  return {
    id,
    kind: "change",
    tracker: "trait:skills/Leadership/",
    amount: -1,
    damage: null,
    before: 2,
    after: 1,
    text: "Learned about Elena's Loyal",
    note: "",
    happened_at: "2026-10-27T20:00:00Z",
    actor_name: "Agnes's player",
    by_staff: false,
    undone,
    undoes: null,
    upkeep: false,
  };
}

describe("others at the game", () => {
  it("finds Leadership among the uses this game", () => {
    const uses = (key: string) => ({ key, name: "x", detail: "", group: "Skills", uses: 2, left: 1, counter_id: null }) as ExpendableOut;
    expect(leadershipOf([uses("trait:backgrounds/Herd/"), uses("trait:skills/Leadership/")])?.key).toBe("trait:skills/Leadership/");
    expect(leadershipOf([uses("trait:backgrounds/Herd/")])).toBeUndefined();
  });

  it("forgets what was learned once its tap is undone", () => {
    expect(shownSeen(seen, [entry("tap-1", false)])).toBe(seen);
    const forgotten = shownSeen(seen, [entry("tap-1", true)]);
    expect([forgotten.known, forgotten.patron, forgotten.story]).toEqual([false, null, null]);
  });

  it("finds others by any part of their name", () => {
    const other = (name: string) => ({ character_id: name, name, pronouns: null, kind: "pc", sect: "Camarilla", same_sect: true, accepted: "Acknowledged", titles: [] }) as OtherOut;
    const all = [other("Elena Varga"), other("Tomas Reyes")];
    expect(matching(all, " varga ").map((o) => o.name)).toEqual(["Elena Varga"]);
    expect(matching(all, "")).toHaveLength(2);
  });
});

describe("an other's line in the list", () => {
  const other = (more: Partial<OtherOut>): OtherOut => ({ character_id: "1", name: "Agnes", pronouns: null, kind: "pc", sect: "Camarilla", same_sect: true, accepted: "Acknowledged", titles: [], ...more });

  it("is its sect and titles", () => {
    expect(sectLine(other({ titles: ["Seneschal"] }))).toBe("Camarilla · Seneschal");
    expect(sectLine(other({ sect: null }))).toBe("No sect");
  });

  it("adds the source it carries tonight, fixed at check-in (#441)", () => {
    expect(sectLine(other({ titles: ["Seneschal"], carried_source: "Elder" }))).toBe("Camarilla · Seneschal · status from Elder tonight");
  });
});
