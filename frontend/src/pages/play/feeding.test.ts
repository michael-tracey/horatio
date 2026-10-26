import { describe, expect, it } from "vitest";
import { clockText, compareText, defaultPlan, fedBlood, feedChoices, feedName, feedNote, giveText, herdFeed, hunt, loadFeeding, loadSound, planText, resultText, saveFeeding, saveSound, type Feeding } from "./feeding";

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
  it("offers the hunt to anyone, and the Herd feed too with Herd", () => {
    expect(feedChoices(0)).toEqual([hunt]);
    for (const herd of [1, 2, 3, 5]) expect(feedChoices(herd)).toEqual([{ minutes: 5, blood: herd, herd }, { minutes: 15, blood: 2, herd: 0 }]);
    expect(planText(herdFeed(3))).toBe("5 minutes, +3 Blood (Herd 3)");
    expect(planText(hunt)).toBe("15 minutes, +2 Blood");
    expect(feedNote(herdFeed(3))).toBe("Fed (Herd 3)");
    expect(feedNote(hunt)).toBe("Fed (hunted)");
    expect(feedName(hunt)).toBe("Hunting");
    expect(feedName(herdFeed(2))).toBe("Feeding from your Herd");
  });

  it("chooses Herd to start with from Herd 2, and the hunt at Herd 0 and 1", () => {
    expect(defaultPlan(0)).toEqual(hunt);
    expect(defaultPlan(1)).toEqual(hunt);
    expect(defaultPlan(2)).toEqual(herdFeed(2));
    expect(defaultPlan(3)).toEqual(herdFeed(3));
    expect(defaultPlan(5)).toEqual(herdFeed(5));
  });

  it("compares the two in a line, by Herd rating", () => {
    expect(compareText(0)).toBe("");
    expect(compareText(1)).toBe("Your Herd is quicker, but hunting gives more Blood");
    expect(compareText(2)).toBe("Both give 2 Blood; your Herd takes a third of the time");
    expect(compareText(3)).toBe("Your Herd is quicker and gives more");
    expect(compareText(5)).toBe("Your Herd is quicker and gives more");
  });

  it("says what each choice gives from the Blood now, capped at the most", () => {
    expect(giveText(hunt, 7, 10)).toBe("+2 Blood: Blood 7 → 9");
    expect(giveText(herdFeed(1), 7, 10)).toBe("+1 Blood: Blood 7 → 8");
    expect(giveText(herdFeed(3), 8, 10)).toBe("+3 Blood, but you'll be full at 10: Blood 8 → 10");
    expect(giveText(hunt, 9, 10)).toBe("+2 Blood, but you'll be full at 10: Blood 9 → 10");
    expect(giveText(hunt, 10, 10)).toBe("Blood is full already, at 10");
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
    const herd = herdFeed(3);
    expect(fedBlood(herd, 7, 10)).toBe(10);
    expect(resultText(herd, { before: 7, after: 10, most: 10 })).toEqual({ gained: "+3 Blood", rest: " (Herd 3): Blood 7 → 10." });
    expect(fedBlood(hunt, 11, 12)).toBe(12);
    expect(resultText(hunt, { before: 11, after: 12, most: 12 })).toEqual({ gained: "+1 Blood", rest: " (hunted), now full: Blood 11 → 12." });
    expect(resultText(hunt, { before: 12, after: 12, most: 12 })).toEqual({ gained: "+0 Blood", rest: " (hunted): Blood was full already, at 12." });
  });

  it("keeps the timer on the device, per character", () => {
    const storage = memory();
    const feeding: Feeding = { tapId: "t1", endsAt: 1_000, plan: herdFeed(2) };
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

  it("reads a plan saved before the choice: with Herd it is the Herd feed, without it the hunt", () => {
    const storage = memory();
    const old = (plan: object) => storage.setItem("horatio.feed.c1", JSON.stringify({ tapId: "t", endsAt: 5, plan }));
    old({ minutes: 5, blood: 3, herd: 3 });
    expect(loadFeeding("c1", storage)?.plan).toEqual(herdFeed(3));
    expect(feedNote(loadFeeding("c1", storage)!.plan)).toBe("Fed (Herd 3)");
    old({ minutes: 15, blood: 2, herd: 0 });
    expect(loadFeeding("c1", storage)?.plan).toEqual(hunt);
    expect(feedNote(loadFeeding("c1", storage)!.plan)).toBe("Fed (hunted)");
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
