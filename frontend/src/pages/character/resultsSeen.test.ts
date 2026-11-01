import { describe, expect, it } from "vitest";
import { isNew, markSeen, NEW_FOR_MS, newResults, seenUpTo } from "./resultsSeen";

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

describe("new downtime results", () => {
  const october = "2026-10-20T19:00:00+00:00";
  const november = "2026-11-20T19:00:00+00:00";

  it("counts what was delivered after the newest result seen on this device", () => {
    expect(newResults([november, october], october)).toBe(1);
    expect(newResults([november, october], november)).toBe(0);
    expect(newResults([], october)).toBe(0);
  });

  it("without a record, counts only what was delivered lately", () => {
    const now = Date.parse(november) + 1000;
    expect(newResults([november, october], null, now)).toBe(1);
    expect(newResults([november], null, Date.parse(november) + NEW_FOR_MS + 1)).toBe(0);
  });

  it("marks one result new by the same rule the count uses", () => {
    expect(isNew(november, october)).toBe(true);
    expect(isNew(october, october)).toBe(false);
    expect(isNew(october, null, Date.parse(october) + 1000)).toBe(true);
    expect(isNew(october, null, Date.parse(october) + NEW_FOR_MS + 1)).toBe(false);
  });

  it("remembers the newest result seen for each character, never going back", () => {
    const storage = memory();
    expect(seenUpTo("agnes", storage)).toBeNull();
    markSeen("agnes", november, storage);
    markSeen("agnes", october, storage);
    expect(seenUpTo("agnes", storage)).toBe(november);
    expect(seenUpTo("bram", storage)).toBeNull();
  });
});
