import { describe, expect, it } from "vitest";
import { keepAwake, loadAwake, saveAwake, type Lockable, type Visible } from "./wakeLock";

/** A browser that grants wake locks (or refuses them), and a page that can be hidden and shown. */
function browser({ refuse = false } = {}) {
  const locks: { released: boolean; release: () => Promise<void>; addEventListener: (type: "release", l: () => void) => void }[] = [];
  const nav: Lockable = {
    wakeLock: {
      request: async () => {
        if (refuse) throw new DOMException("Low battery", "NotAllowedError");
        const listeners: (() => void)[] = [];
        const lock = {
          released: false,
          release: async () => {
            if (lock.released) return;
            lock.released = true;
            listeners.forEach((l) => l());
          },
          addEventListener: (_type: "release", l: () => void) => void listeners.push(l),
        };
        locks.push(lock);
        return lock;
      },
    },
  };
  const page = new EventTarget() as EventTarget & { visibilityState: DocumentVisibilityState };
  page.visibilityState = "visible";
  const show = (state: DocumentVisibilityState) => {
    page.visibilityState = state;
    // Hiding the page lets go of the lock, as browsers do.
    if (state === "hidden") locks.forEach((l) => void l.release());
    page.dispatchEvent(new Event("visibilitychange"));
  };
  const seen: boolean[] = [];
  return { nav, doc: page as unknown as Visible, locks, show, seen, onChange: (held: boolean) => void seen.push(held) };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("keepAwake", () => {
  it("holds the screen awake, and lets go when stopped", async () => {
    const b = browser();
    const stop = keepAwake(b.nav, b.doc, b.onChange);
    await settle();
    expect(b.locks).toHaveLength(1);
    expect(b.seen).toEqual([true]);
    stop();
    await settle();
    expect(b.locks[0]!.released).toBe(true);
    expect(b.seen).toEqual([true, false]);
  });

  it("asks again when the page is shown after being hidden", async () => {
    const b = browser();
    const stop = keepAwake(b.nav, b.doc, b.onChange);
    await settle();
    b.show("hidden");
    await settle();
    expect(b.seen).toEqual([true, false]);
    b.show("visible");
    await settle();
    expect(b.locks).toHaveLength(2);
    expect(b.locks[1]!.released).toBe(false);
    expect(b.seen).toEqual([true, false, true]);
    stop();
  });

  it("waits for a hidden page to be shown", async () => {
    const b = browser();
    b.show("hidden");
    const stop = keepAwake(b.nav, b.doc, b.onChange);
    await settle();
    expect(b.locks).toHaveLength(0);
    b.show("visible");
    await settle();
    expect(b.locks).toHaveLength(1);
    stop();
  });

  it("asks no more once stopped", async () => {
    const b = browser();
    const stop = keepAwake(b.nav, b.doc, b.onChange);
    stop(); // before the browser answers
    await settle();
    expect(b.locks[0]!.released).toBe(true);
    b.show("hidden");
    b.show("visible");
    await settle();
    expect(b.locks).toHaveLength(1);
  });

  it("does nothing where the browser has no wake lock, or refuses one", async () => {
    const none = browser();
    const changes: boolean[] = [];
    keepAwake({}, none.doc, (held) => changes.push(held))();
    expect(changes).toEqual([]);

    const refused = browser({ refuse: true });
    keepAwake(refused.nav, refused.doc, refused.onChange);
    await settle();
    expect(refused.seen).toEqual([false]);
  });
});

describe("the Play View's own keep-awake switch, remembered on the device", () => {
  function memory(): Storage {
    const items = new Map<string, string>();
    return {
      get length() {
        return items.size;
      },
      clear: () => items.clear(),
      getItem: (k) => items.get(k) ?? null,
      key: (i) => [...items.keys()][i] ?? null,
      removeItem: (k) => void items.delete(k),
      setItem: (k, v) => void items.set(k, v),
    };
  }

  it("follows the settings until it is used, then keeps its choice", () => {
    const storage = memory();
    expect(loadAwake(storage)).toBeNull();
    saveAwake(false, storage);
    expect(loadAwake(storage)).toBe(false);
    saveAwake(true, storage);
    expect(loadAwake(storage)).toBe(true);
    saveAwake(null, storage);
    expect(loadAwake(storage)).toBeNull();
  });

  it("keeps nothing where the browser refuses to keep anything", () => {
    const refuse = () => {
      throw new DOMException("Blocked", "SecurityError");
    };
    const refusing = { ...memory(), getItem: refuse, setItem: refuse, removeItem: refuse };
    expect(loadAwake(refusing)).toBeNull();
    expect(() => saveAwake(true, refusing)).not.toThrow();
  });
});
