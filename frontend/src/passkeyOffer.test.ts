import { describe, expect, it } from "vitest";
import { forgetPasswordSignIn, markPasswordSignIn, offerAnswered, offerDue } from "./passkeyOffer";

/** A Storage kept in memory. */
function memory(): Storage {
  const kept = new Map<string, string>();
  return {
    get length() {
      return kept.size;
    },
    clear: () => kept.clear(),
    getItem: (key) => kept.get(key) ?? null,
    key: (i) => [...kept.keys()][i] ?? null,
    removeItem: (key) => void kept.delete(key),
    setItem: (key, value) => void kept.set(key, value),
  };
}

describe("the passkey offer, once on each device (#1193)", () => {
  it("is due only after a password sign-in in this tab", () => {
    const s = { session: memory(), local: memory() };
    expect(offerDue(s)).toBe(false);
    markPasswordSignIn(s);
    expect(offerDue(s)).toBe(true);
    forgetPasswordSignIn(s);
    expect(offerDue(s)).toBe(false);
  });

  it("isn't offered again on the device once answered, even in a new tab", () => {
    const local = memory();
    const first = { session: memory(), local };
    markPasswordSignIn(first);
    offerAnswered(first);
    expect(offerDue(first)).toBe(false);
    const again = { session: memory(), local };
    markPasswordSignIn(again);
    expect(offerDue(again)).toBe(false);
  });

  it("offers nothing where storage can't be used", () => {
    const broken = memory();
    broken.getItem = () => {
      throw new Error("blocked");
    };
    expect(offerDue({ session: broken, local: broken })).toBe(false);
    expect(() => offerAnswered({ session: broken, local: broken })).not.toThrow();
  });
});
