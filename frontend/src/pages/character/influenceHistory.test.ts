import { describe, expect, it } from "vitest";
import type { HistoryEntryOut, InfluenceStandingOut } from "../../api/types";
import { datesFor } from "../../dates";
import { blocksText, filterHistory, historySource, monthText, NO_HISTORY_FILTERS, thisMonth } from "./influenceHistory";

const dates = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });

function entry(change: Partial<HistoryEntryOut>): HistoryEntryOut {
  return {
    id: "1",
    short_id: "E1",
    troupe_id: "t",
    troupe_name: "Lords of the Night",
    other_troupe: false,
    type: "elite",
    happened_at: "2026-10-10T23:00:00Z",
    specialization: "Police",
    action_key: "smooth_over",
    action: "4: Smooth Over",
    conflict: false,
    purpose: "",
    times: 1,
    own_blocks: 0,
    source: "downtime",
    cycle_id: null,
    cycle_name: null,
    game_number: null,
    game_started_at: null,
    needs_details: false,
    can_finish: false,
    findable: true,
    ...change,
  };
}

const standing = (type: "elite" | "underworld", rating: number): InfluenceStandingOut => ({
  action_kind: `influence_${type}`,
  type,
  rating,
  held: [],
  options: [],
  actions: [],
});

describe("a character's influence history", () => {
  const entries = [
    entry({ id: "a", type: "underworld", specialization: "Docks", findable: false, happened_at: "2026-07-01T12:00:00Z" }),
    entry({ id: "b", happened_at: "2026-07-12T03:30:00Z" }), // 11 Jul, 11:30 pm in New York
    entry({ id: "c", happened_at: "2026-07-12T04:30:00Z" }), // 12 Jul
  ];
  const ids = (filters: Partial<typeof NO_HISTORY_FILTERS>) => filterHistory(entries, { ...NO_HISTORY_FILTERS, ...filters }, dates).map((e) => e.id);

  it("filters by type, specialisation, days in the reader's zone, and what is findable now", () => {
    expect(ids({})).toEqual(["a", "b", "c"]);
    expect(ids({ type: "underworld" })).toEqual(["a"]);
    expect(ids({ specialization: "Police" })).toEqual(["b", "c"]);
    expect(ids({ from: "2026-07-11", to: "2026-07-11" })).toEqual(["b"]);
    expect(ids({ findable: true })).toEqual(["b", "c"]);
  });

  it("says only the character's own blocks", () => {
    expect(blocksText(0)).toBeNull();
    expect(blocksText(1)).toBe("you blocked it once");
    expect(blocksText(2)).toBe("you blocked it twice");
    expect(blocksText(3)).toBe("you blocked it 3 times");
  });

  it("says where it came from", () => {
    expect(historySource({ source: "downtime", cycle_name: "November", game_number: null })).toBe("Downtime: November");
    expect(historySource({ source: "game", cycle_name: null, game_number: 3 })).toBe("At a game (game 3)");
    expect(historySource({ source: "hand", cycle_name: null, game_number: null })).toBe("Logged by staff");
    expect(historySource({ source: "hand", cycle_name: "November", game_number: null })).toBe("Logged by staff, for November");
    expect(historySource({ source: "quest", cycle_name: "November", game_number: null })).toBe("For a quest, in November");
  });

  it("sums up this month's actions, where they were spent, and what is owed", () => {
    const now = new Date("2026-10-21T12:00:00Z");
    const history = {
      entries: [
        entry({ source: "game" }),
        entry({ source: "downtime", times: 2 }),
        entry({ happened_at: "2026-09-30T12:00:00Z" }), // last month
      ],
      standings: [standing("elite", 4), standing("underworld", 0)],
      owed: [
        { type: "elite" as const, amount: 1 },
        { type: "underworld" as const, amount: 0 },
      ],
    };
    const [elite, ...rest] = thisMonth(history, dates, now);
    expect(rest).toEqual([]); // no Underworld, none used, none owed
    expect(monthText(elite!)).toBe("3 of 4 spent: 1 at a game, 2 in downtimes. 1 owed to the next cycle.");
    expect(monthText({ ...elite!, rating: 0, owed: 0 })).toBe("3 spent: 1 at a game, 2 in downtimes.");
  });
});
