import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadChanging, saveChanging, useChanging } from "./sheetMode";

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

const broken = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
} as unknown as Storage;

describe("Make changes, remembered on this device", () => {
  it("is off until it is turned on", () => {
    expect(loadChanging("c1", memory())).toBe(false);
  });

  it("remembers on and off for each character", () => {
    const storage = memory();
    saveChanging("c1", true, storage);
    expect(loadChanging("c1", storage)).toBe(true);
    expect(loadChanging("c2", storage)).toBe(false);
    saveChanging("c1", false, storage);
    expect(loadChanging("c1", storage)).toBe(false);
    expect(storage.length).toBe(0);
  });

  it("is off, and saving does nothing, when storage is out of reach", () => {
    expect(loadChanging("c1", broken)).toBe(false);
    expect(() => saveChanging("c1", true, broken)).not.toThrow();
  });
});

describe("useChanging", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("turns on and off, keeps it in this browser, and shares it with the rest of the page", () => {
    const one = renderHook(() => useChanging("h1"));
    const other = renderHook(() => useChanging("h1"));
    expect(one.result.current[0]).toBe(false);
    act(() => one.result.current[1](true));
    expect(one.result.current[0]).toBe(true);
    expect(other.result.current[0]).toBe(true);
    expect(loadChanging("h1")).toBe(true);
    act(() => one.result.current[1](false));
    expect(other.result.current[0]).toBe(false);
    expect(loadChanging("h1")).toBe(false);
  });

  it("starts from what this browser remembers", () => {
    saveChanging("h2", true);
    expect(renderHook(() => useChanging("h2")).result.current[0]).toBe(true);
  });

  it("still turns on and off for this visit when storage is out of reach", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useChanging("h3"));
    expect(result.current[0]).toBe(false);
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
  });
});
