import { describe, expect, it, vi } from "vitest";
import { isLoadFailure, reloadOnce } from "./staleBuild";

function memory(): Storage {
  const m = new Map<string, string>();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k), clear: () => m.clear(), key: () => null, length: 0 };
}

describe("reloadOnce", () => {
  it("reloads the first time and not again within a minute", () => {
    const reload = vi.fn();
    const s = memory();
    expect(reloadOnce(s, 1000, reload)).toBe(true);
    expect(reloadOnce(s, 5000, reload)).toBe(false);
    expect(reloadOnce(s, 70_000, reload)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
  it("does not reload when the guard cannot be kept", () => {
    const reload = vi.fn();
    const broken = { ...memory(), setItem: () => { throw new Error("full"); } } as Storage;
    expect(reloadOnce(broken, 1, reload)).toBe(false);
    expect(reloadOnce(undefined, 1, reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});

it("knows a failed page load", () => {
  expect(isLoadFailure(new TypeError("error loading dynamically imported module: /assets/A.js"))).toBe(true);
  expect(isLoadFailure(new TypeError("Importing a module script failed."))).toBe(true);
  expect(isLoadFailure(new Error("x is undefined"))).toBe(false);
});
