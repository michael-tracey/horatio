import { useCallback, useEffect, useRef, useState } from "react";
import { askToFlip, loadAsked, loadFlipping, needsAsking, saveAsked, saveFlipping, START, step, tilt, type OrientationHost } from "./flip";

/** With no reading this long, the phone either has no sensor or (iOS) must be asked first. */
const SILENT_MS = 1500;

/**
 * Whether the sensor has sent a reading while this page has been open. The Play View
 * remakes the Throws tab when the sheet arrives (#837), and the new tab offers the
 * switch at once rather than waiting for the next reading.
 */
let sensorSeen = false;

/** For tests: as if the sensor had never sent a reading. */
export function forgetSensor(): void {
  sensorSeen = false;
}

type Host = OrientationHost & Pick<Window, "addEventListener" | "removeEventListener">;
type Visible = Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;

export type Flipping = {
  /**
   * What to offer: nothing (`none`: no sensor, or none found yet), a button that
   * asks (`ask`, on iOS), a note that the phone said no (`denied`), or the switch
   * (`ready`).
   */
  support: "none" | "ask" | "denied" | "ready";
  /** "Throw by flipping" on this device, on unless turned off. */
  on: boolean;
  setOn: (on: boolean) => void;
  /** Ask for the sensor; call it straight from a tap, as iOS requires. */
  ask: () => void;
};

/**
 * Throw by flipping the phone (#669) while the Throws tab is showing: listens to
 * the orientation sensor only while the page is visible, and only while flipping
 * is on (or, with it off, just long enough to learn the phone has a sensor, so the
 * switch can be offered). Calls `onFlip` once per flip.
 */
export function useFlip(onFlip: () => void, host: Host = window, doc: Visible = document, coarse: () => boolean = touchScreen): Flipping {
  const asks = needsAsking(host);
  const [on, setOnState] = useState(loadFlipping);
  const [asked, setAsked] = useState(loadAsked);
  const [askedNow, setAskedNow] = useState(false);
  const [sensed, setSensed] = useState(() => sensorSeen);
  const [silent, setSilent] = useState(false);
  const [visible, setVisible] = useState(doc.visibilityState === "visible");
  const flip = useRef(onFlip);
  flip.current = onFlip;
  const flipping = useRef(on);
  flipping.current = on;

  useEffect(() => {
    const seen = () => setVisible(doc.visibilityState === "visible");
    doc.addEventListener("visibilitychange", seen);
    return () => doc.removeEventListener("visibilitychange", seen);
  }, [doc]);

  // Listen first, before any asking: Android, and Chrome even where it could ask,
  // send readings straight away; iOS sends none until it is asked.
  const listen = visible && (on || !sensed);

  useEffect(() => {
    if (!listen) return;
    let state = START;
    const read = (e: Event) => {
      const { beta, gamma } = e as DeviceOrientationEvent;
      if (tilt(beta, gamma) === null) return;
      sensorSeen = true;
      setSensed(true);
      if (!flipping.current) return;
      const out = step(state, { beta, gamma, at: performance.now() });
      state = out.state;
      if (out.flipped) flip.current();
    };
    host.addEventListener("deviceorientation", read);
    return () => host.removeEventListener("deviceorientation", read);
  }, [listen, host]);

  useEffect(() => {
    if (sensed || !listen) return;
    const t = window.setTimeout(() => setSilent(true), SILENT_MS);
    return () => window.clearTimeout(t);
  }, [sensed, listen]);

  const ask = useCallback(() => {
    void askToFlip(host).then((yes) => {
      const answer = yes ? "granted" : "denied";
      saveAsked(answer);
      setAsked(answer);
      setAskedNow(true);
      if (yes) {
        saveFlipping(true);
        setOnState(true);
      }
    });
  }, [host]);

  const setOn = useCallback((next: boolean) => {
    saveFlipping(next);
    setOnState(next);
  }, []);

  let support: Flipping["support"] = "none";
  if (sensed) support = "ready";
  // Only a touch phone that must ask, and has sent nothing yet, is offered the asking button; once
  // asked this visit with still nothing, it has no sensor. A desktop never is.
  else if (asks && silent && coarse()) support = asked === "denied" ? "denied" : askedNow ? "none" : "ask";
  return { support, on, setOn, ask };
}

/** A phone or tablet: its main pointer is a finger. */
function touchScreen(): boolean {
  try {
    return !!window.matchMedia?.("(pointer: coarse)").matches;
  } catch {
    return false;
  }
}
