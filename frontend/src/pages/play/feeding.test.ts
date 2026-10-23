import { describe, expect, it } from "vitest";
import { clockText, fedBlood, feedNote, feedPlan, loadFeeding, loadSound, planText, resultText, saveFeeding, saveSound, type Feeding } from "./feeding";

function memory(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  };
}

describe("feeding at a game", () => {
  it("takes 15 minutes for 2 Blood, or 5 for Blood equal to Herd", () => {
    expect(feedPlan(0)).toEqual({ minutes: 15, blood: 2, herd: 0 });
    expect(feedPlan(3)).toEqual({ minutes: 5, blood: 3, herd: 3 });
    expect(planText(feedPlan(3))).toBe("5 minutes, +3 Blood (Herd 3)");
    expect(planText(feedPlan(0))).toBe("15 minutes, +2 Blood");
    expect(feedNote(feedPlan(3))).toBe("Fed (Herd 3)");
    expect(feedNote(feedPlan(0))).toBe("Fed");
  });

  it("counts down in minutes and seconds, rounding up", () => {
    expect(clockText(15 * 60_000)).toBe("15:00");
    expect(clockText(299_001)).toBe("05:00");
    expect(clockText(299_000)).toBe("04:59");
    expect(clockText(400)).toBe("00:01");
    expect(clockText(0)).toBe("00:00");
    expect(clockText(-5000)).toBe("00:00");
  });

  it("caps the Blood at the most, and says so", () => {
    const herd = feedPlan(3);
    expect(fedBlood(herd, 7, 10)).toBe(10);
    expect(resultText(herd, { before: 7, after: 10, most: 10 })).toEqual({ gained: "+3 Blood", rest: " (Herd 3): Blood 7 → 10." });
    expect(fedBlood(feedPlan(0), 11, 12)).toBe(12);
    expect(resultText(feedPlan(0), { before: 11, after: 12, most: 12 })).toEqual({ gained: "+1 Blood", rest: ", now full: Blood 11 → 12." });
    expect(resultText(feedPlan(0), { before: 12, after: 12, most: 12 })).toEqual({ gained: "+0 Blood", rest: ": Blood was full already, at 12." });
  });

  it("keeps the timer on the device, per character", () => {
    const storage = memory();
    const feeding: Feeding = { tapId: "t1", endsAt: 1_000, plan: feedPlan(2) };
    saveFeeding("c1", feeding, storage);
    expect(loadFeeding("c1", storage)).toEqual(feeding);
    expect(loadFeeding("c2", storage)).toBeNull();
    saveFeeding("c1", null, storage);
    expect(storage.length).toBe(0);

    storage.setItem("horatio.feed.c1", "{not json");
    expect(loadFeeding("c1", storage)).toBeNull();
    storage.setItem("horatio.feed.c1", JSON.stringify({ endsAt: 5 }));
    expect(loadFeeding("c1", storage)).toBeNull();
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(loadFeeding("c1", broken)).toBeNull();
    expect(() => saveFeeding("c1", feeding, broken)).not.toThrow();
  });

  it("plays its sound unless it was turned off on this device", () => {
    const storage = memory();
    expect(loadSound(storage)).toBe(true);
    saveSound(false, storage);
    expect(loadSound(storage)).toBe(false);
    saveSound(true, storage);
    expect(loadSound(storage)).toBe(true);
  });
});
