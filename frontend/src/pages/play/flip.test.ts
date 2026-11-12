import { describe, expect, it, vi } from "vitest";
import {
  askToFlip,
  COOLDOWN_MS,
  FLIP_MS,
  flipsIn,
  loadAsked,
  loadFlipping,
  needsAsking,
  saveAsked,
  saveFlipping,
  START,
  step,
  tilt,
  TURN_MS,
  type Reading,
} from "./flip";

/** Readings every 16 ms (60 a second, as phones send them), turning beta from one angle to another. */
function turn(from: number, to: number, ms: number, start: number, gamma = 0): Reading[] {
  const n = Math.max(1, Math.round(ms / 16));
  return Array.from({ length: n + 1 }, (_, i) => ({ beta: from + ((to - from) * i) / n, gamma, at: start + (ms * i) / n }));
}

/** Holding still at one angle for a while. */
function hold(beta: number, ms: number, start: number, gamma = 0): Reading[] {
  return turn(beta, beta, ms, start, gamma);
}

/** Readings laid end to end in time. */
function seq(...parts: ((start: number) => Reading[])[]): Reading[] {
  const out: Reading[] = [];
  let t = 0;
  for (const part of parts) {
    const rs = part(t);
    out.push(...rs);
    t = rs[rs.length - 1]!.at + 16;
  }
  return out;
}

/** A flip in the hand: face up, over to face down quickly, and back up. */
const flip = (downFor = 200, turnMs = 300) => [
  (s: number) => turn(0, 180, turnMs, s),
  (s: number) => hold(180, downFor, s),
  (s: number) => turn(180, 0, turnMs, s),
];

describe("tilt", () => {
  it("is 0 face up, 180 face down, and 90 upright either way", () => {
    expect(tilt(0, 0)).toBeCloseTo(0);
    expect(tilt(180, 0)).toBeCloseTo(180);
    expect(tilt(-180, 0)).toBeCloseTo(180);
    expect(tilt(90, 0)).toBeCloseTo(90);
    expect(tilt(0, 90)).toBeCloseTo(90);
  });

  it("combines both tilts: flipped over sideways is face down too", () => {
    expect(tilt(0, -90)).toBeCloseTo(90);
    // Upside down front to back and on its side at once still faces down a long way.
    expect(tilt(170, 20)!).toBeGreaterThan(150);
  });

  it("has nothing for a browser with no reading", () => {
    expect(tilt(null, 0)).toBeNull();
    expect(tilt(0, null)).toBeNull();
    expect(tilt(Number.NaN, 0)).toBeNull();
  });
});

describe("the flip detector", () => {
  it("throws once for a flip in the hand", () => {
    expect(flipsIn(seq((s) => hold(0, 300, s), ...flip(), (s) => hold(0, 500, s)))).toBe(1);
  });

  it("throws for a flip over sideways too", () => {
    const sideways = seq(
      (s) => hold(0, 200, s),
      (s) => Array.from({ length: 20 }, (_, i) => ({ beta: 0, gamma: -(i * 9), at: s + i * 16 })),
      (s) => Array.from({ length: 10 }, (_, i) => ({ beta: 180, gamma: 10, at: s + i * 16 })),
      (s) => turn(180, 0, 300, s),
    );
    expect(flipsIn(sideways)).toBe(1);
  });

  it("throws for each of two flips with time between", () => {
    expect(flipsIn(seq((s) => hold(0, 200, s), ...flip(), (s) => hold(0, COOLDOWN_MS + 200, s), ...flip(), (s) => hold(0, 200, s)))).toBe(2);
  });

  it("ignores a second flip straight after the first, so one flip throws once", () => {
    expect(flipsIn(seq((s) => hold(0, 100, s), ...flip(100, 200), ...flip(100, 200), (s) => hold(0, 200, s)))).toBe(1);
  });

  it("doesn't throw for a slow turn over", () => {
    expect(flipsIn(seq((s) => hold(0, 200, s), ...flip(200, TURN_MS + 1200), (s) => hold(0, 200, s)))).toBe(0);
  });

  it("doesn't throw for tilting the phone to read it, or holding it upright", () => {
    expect(flipsIn(seq((s) => hold(0, 200, s), (s) => turn(0, 120, 300, s), (s) => hold(120, 800, s), (s) => turn(120, 0, 300, s)))).toBe(0);
    expect(flipsIn(seq((s) => hold(80, 2000, s, 10)))).toBe(0);
  });

  it("doesn't throw for a phone set face down on a table, nor when it's picked up again", () => {
    expect(flipsIn(seq((s) => hold(0, 200, s), (s) => turn(0, 180, 400, s), (s) => hold(180, FLIP_MS + 3000, s), (s) => turn(180, 0, 400, s), (s) => hold(0, 500, s)))).toBe(0);
  });

  it("doesn't throw coming out of a pocket face down", () => {
    expect(flipsIn(seq((s) => hold(170, 3000, s, 15), (s) => turn(170, 0, 400, s), (s) => hold(0, 300, s)))).toBe(0);
  });

  it("skips readings with nothing in them", () => {
    const readings = seq((s) => hold(0, 200, s), ...flip());
    const gappy = readings.flatMap((r, i) => (i % 3 ? [r] : [r, { beta: null, gamma: null, at: r.at + 1 }]));
    expect(flipsIn(gappy)).toBe(1);
  });

  it("starts idle, so a phone first seen face down can't throw by coming up", () => {
    const { state } = step(START, { beta: 180, gamma: 0, at: 0 });
    expect(state.phase).toBe("idle");
    expect(step(state, { beta: 0, gamma: 0, at: 300 }).flipped).toBe(false);
  });
});

describe("asking for the sensor", () => {
  it("needs asking only where the browser has requestPermission (iOS)", () => {
    expect(needsAsking({})).toBe(false);
    expect(needsAsking({ DeviceOrientationEvent: {} })).toBe(false);
    expect(needsAsking({ DeviceOrientationEvent: { requestPermission: () => Promise.resolve("granted") } })).toBe(true);
  });

  it("is allowed with no asking where the browser doesn't ask", async () => {
    expect(await askToFlip({ DeviceOrientationEvent: {} })).toBe(true);
  });

  it("is allowed when the person says yes, and not when they say no", async () => {
    const yes = vi.fn(() => Promise.resolve("granted" as const));
    expect(await askToFlip({ DeviceOrientationEvent: { requestPermission: yes } })).toBe(true);
    expect(yes).toHaveBeenCalledOnce();
    expect(await askToFlip({ DeviceOrientationEvent: { requestPermission: () => Promise.resolve("denied" as const) } })).toBe(false);
  });

  it("isn't allowed when asking fails, as it does without a tap", async () => {
    expect(await askToFlip({ DeviceOrientationEvent: { requestPermission: () => Promise.reject(new Error("needs a tap")) } })).toBe(false);
  });
});

describe("what's kept on the device", () => {
  function memory(): Storage {
    const m = new Map<string, string>();
    return {
      getItem: (k) => m.get(k) ?? null,
      setItem: (k, v) => void m.set(k, v),
      removeItem: (k) => void m.delete(k),
      clear: () => m.clear(),
      key: () => null,
      get length() {
        return m.size;
      },
    };
  }

  it("throws by flipping unless turned off", () => {
    const s = memory();
    expect(loadFlipping(s)).toBe(true);
    saveFlipping(false, s);
    expect(loadFlipping(s)).toBe(false);
    saveFlipping(true, s);
    expect(loadFlipping(s)).toBe(true);
  });

  it("remembers iOS's answer", () => {
    const s = memory();
    expect(loadAsked(s)).toBeNull();
    saveAsked("denied", s);
    expect(loadAsked(s)).toBe("denied");
    saveAsked("granted", s);
    expect(loadAsked(s)).toBe("granted");
  });

  it("copes with storage that throws", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(loadFlipping(broken)).toBe(true);
    expect(loadAsked(broken)).toBeNull();
    expect(() => saveFlipping(false, broken)).not.toThrow();
    expect(() => saveAsked("granted", broken)).not.toThrow();
  });
});
