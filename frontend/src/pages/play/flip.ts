/**
 * Throwing by flipping the phone (#669): face down in the hand and back up again,
 * as two players flip together across a table. The phone's orientation sensor
 * (`deviceorientation`) gives the screen's tilt; this file turns a run of readings
 * into "a flip happened", and keeps everything else (a slow tilt, a phone set down
 * on a table, one put in a pocket) from counting.
 *
 * The thresholds are constants so they can be tuned on real phones.
 */

/** Within this many degrees of flat, screen up, the phone counts as face up. */
export const FACE_UP_MAX = 45;
/** Past this many degrees from face up, the screen counts as face down. */
export const FACE_DOWN_MIN = 150;
/** The turn down, from leaving face up to face down, must take no longer: a slow tilt isn't a flip. */
export const TURN_MS = 800;
/** Once face down, the screen must come back face up within this: a phone set down stays down. */
export const FLIP_MS = 1500;
/** After a flip throws, flips are ignored this long, so one flip throws once. */
export const COOLDOWN_MS = 1200;

/** One reading from `deviceorientation`: degrees, and when it came (ms). */
export type Reading = { beta: number | null; gamma: number | null; at: number };

/**
 * How far the screen is turned from facing straight up, from 0 (flat, face up) to
 * 180 (flat, face down). `beta` is the tilt front to back and `gamma` side to side;
 * with the browser's Z-X'-Y'' rotation order the screen's normal makes an angle
 * whose cosine is cos(beta)·cos(gamma) with the vertical. Null when the browser
 * has no reading (desktops send nulls).
 */
export function tilt(beta: number | null, gamma: number | null): number | null {
  if (beta === null || gamma === null || !Number.isFinite(beta) || !Number.isFinite(gamma)) return null;
  const rad = Math.PI / 180;
  const c = Math.cos(beta * rad) * Math.cos(gamma * rad);
  return Math.acos(Math.max(-1, Math.min(1, c))) / rad;
}

/**
 * Where the detector is:
 * - `idle`: not face up, so no flip can start (a phone lying face down, in a pocket);
 * - `up`: face up, ready;
 * - `turning`: left face up at `since`, on the way down;
 * - `down`: reached face down at `since`, waiting to come back up.
 * `quietUntil` is when the cooldown after the last flip ends.
 */
export type FlipState = { phase: "idle" | "up" | "turning" | "down"; since: number; quietUntil: number };

export const START: FlipState = { phase: "idle", since: 0, quietUntil: 0 };

/**
 * The detector's next state after a reading, and whether that reading completed a
 * flip. A flip is face up, then face down within `TURN_MS`, then face up again
 * within `FLIP_MS` of going down, outside the cooldown. Readings with no tilt are
 * skipped.
 */
export function step(state: FlipState, reading: Reading): { state: FlipState; flipped: boolean } {
  const t = tilt(reading.beta, reading.gamma);
  if (t === null) return { state, flipped: false };
  const now = reading.at;
  const up = t <= FACE_UP_MAX;
  const down = t >= FACE_DOWN_MIN;
  const next = (phase: FlipState["phase"], since = now): FlipState => ({ phase, since, quietUntil: state.quietUntil });

  switch (state.phase) {
    case "idle":
      return { state: up ? next("up") : state, flipped: false };
    case "up":
      if (up) return { state, flipped: false };
      if (down) return { state: next("down"), flipped: false };
      return { state: next("turning"), flipped: false };
    case "turning":
      if (up) return { state: next("up"), flipped: false };
      if (now - state.since > TURN_MS) return { state: next("idle"), flipped: false };
      return { state: down ? next("down") : state, flipped: false };
    case "down":
      if (up) {
        const inTime = now - state.since <= FLIP_MS;
        const quiet = now < state.quietUntil;
        if (inTime && !quiet) return { state: { phase: "up", since: now, quietUntil: now + COOLDOWN_MS }, flipped: true };
        return { state: next("up"), flipped: false };
      }
      // Too long face down: set down on a table, or in a pocket.
      if (now - state.since > FLIP_MS) return { state: next("idle"), flipped: false };
      return { state, flipped: false };
  }
}

/** Run a whole sequence of readings through the detector; how many flips it saw. For tests and tuning. */
export function flipsIn(readings: readonly Reading[], from: FlipState = START): number {
  let state = from;
  let flips = 0;
  for (const r of readings) {
    const out = step(state, r);
    state = out.state;
    if (out.flipped) flips += 1;
  }
  return flips;
}

/** What this device can do about flipping. */
export type FlipSupport =
  /** No orientation sensor, or the browser gives no readings: don't offer it. */
  | "none"
  /** iOS: allowed only after asking, from a tap. */
  | "ask"
  /** The sensor works with no asking (Android), or the person has said yes. */
  | "ready";

/** The parts of the browser this uses, so tests can stand in for them. */
export type OrientationHost = { DeviceOrientationEvent?: unknown };

/** iOS's extra: the event's constructor asks for the sensor. */
type Asking = { requestPermission?: () => Promise<"granted" | "denied" | "default"> };

function asking(host: OrientationHost): Asking | undefined {
  const e = host.DeviceOrientationEvent;
  return e && (typeof e === "object" || typeof e === "function") ? (e as Asking) : undefined;
}

/** Whether this browser makes the page ask before it reads the sensor (iOS 13 and later). */
export function needsAsking(host: OrientationHost): boolean {
  return typeof asking(host)?.requestPermission === "function";
}

/**
 * Ask for the sensor, as iOS requires, from a tap. True when allowed. A browser
 * that doesn't ask allows it; one that throws (no tap, or no sensor) doesn't.
 */
export async function askToFlip(host: OrientationHost): Promise<boolean> {
  const event = asking(host);
  const ask = event?.requestPermission;
  if (typeof ask !== "function") return true;
  try {
    return (await ask.call(event)) === "granted";
  } catch {
    return false;
  }
}

const FLIP_KEY = "horatio.throwByFlipping";
const ASKED_KEY = "horatio.flipAsked";

/** The person's choice on this device: "Throw by flipping" on (the default) or off. */
export function loadFlipping(storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    return storage?.getItem(FLIP_KEY) !== "off";
  } catch {
    return true;
  }
}

export function saveFlipping(on: boolean, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    storage?.setItem(FLIP_KEY, on ? "on" : "off");
  } catch {
    // Private windows keep nothing; the choice lasts the visit.
  }
}

/** The answer iOS gave when asked, remembered on this device: "granted", "denied", or null if never asked. */
export function loadAsked(storage: Storage | undefined = globalThis.localStorage): "granted" | "denied" | null {
  try {
    const raw = storage?.getItem(ASKED_KEY);
    return raw === "granted" || raw === "denied" ? raw : null;
  } catch {
    return null;
  }
}

export function saveAsked(answer: "granted" | "denied", storage: Storage | undefined = globalThis.localStorage): void {
  try {
    storage?.setItem(ASKED_KEY, answer);
  } catch {
    // Asked again next visit.
  }
}
