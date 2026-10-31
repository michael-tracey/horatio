import { useCallback, useEffect, useState } from "react";

/** The parts of the Screen Wake Lock API used here, so tests can stand in for the browser. */
type Sentinel = { released: boolean; release: () => Promise<void>; addEventListener: (type: "release", listener: () => void) => void };
export type Lockable = { wakeLock?: { request: (type: "screen") => Promise<Sentinel> } };
export type Visible = Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;

/**
 * Keep the screen from dimming or locking until the returned function is called.
 * The browser lets go of the lock whenever the page is hidden (another app, the
 * phone locked), so it is asked for again each time the page is shown. Says
 * whether the lock is held through `onChange`. Where the browser has no wake
 * lock, or refuses one (low battery, say), nothing happens.
 */
export function keepAwake(nav: Lockable, doc: Visible, onChange: (held: boolean) => void): () => void {
  const wakeLock = nav.wakeLock;
  if (!wakeLock) return () => {};
  let held: Sentinel | null = null;
  let asking = false;
  let stopped = false;

  const ask = async () => {
    if (stopped || asking || held || doc.visibilityState !== "visible") return;
    asking = true;
    try {
      const sentinel = await wakeLock.request("screen");
      if (stopped) {
        await sentinel.release();
        return;
      }
      held = sentinel;
      sentinel.addEventListener("release", () => {
        if (held === sentinel) held = null;
        onChange(false);
      });
      onChange(true);
    } catch {
      onChange(false);
    } finally {
      asking = false;
    }
  };
  const shown = () => void ask();

  doc.addEventListener("visibilitychange", shown);
  void ask();
  return () => {
    stopped = true;
    doc.removeEventListener("visibilitychange", shown);
    if (held && !held.released) void held.release();
  };
}

/** Keep the screen awake while `on` and the page is open; whether it is held now. */
export function useWakeLock(on: boolean): boolean {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!on) return;
    const stop = keepAwake(navigator as Lockable, document, setHeld);
    return () => {
      stop();
      setHeld(false);
    };
  }, [on]);
  return held;
}

const AWAKE = "horatio.keepAwake";

/** This device's own choice from the Play View's switch, or null to follow the settings. */
export function loadAwake(storage: Storage | undefined = globalThis.localStorage): boolean | null {
  try {
    const raw = storage?.getItem(AWAKE);
    return raw === "on" ? true : raw === "off" ? false : null;
  } catch {
    return null;
  }
}

export function saveAwake(on: boolean | null, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (on === null) storage?.removeItem(AWAKE);
    else storage?.setItem(AWAKE, on ? "on" : "off");
  } catch {
    // Private windows keep nothing; the choice lasts the visit.
  }
}

/**
 * Whether the Play View keeps the screen awake (issue #358): the switch in its
 * header, remembered on this device, or until it is used, the "Keep the screen
 * awake" setting, which is on unless turned off. Gives the choice, a way to
 * change it, and whether the lock is held now.
 */
export function useKeepAwake(setting: boolean): { on: boolean; set: (on: boolean) => void; held: boolean } {
  const [chosen, setChosen] = useState(loadAwake);
  const on = chosen ?? setting;
  const held = useWakeLock(on);
  const set = useCallback((next: boolean) => {
    saveAwake(next);
    setChosen(next);
  }, []);
  return { on, set, held };
}
