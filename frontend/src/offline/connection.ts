import { onlineManager } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

/**
 * Whether there is a connection, as the app acts on it (#502). The browser's own
 * word starts it, and its online and offline events change it. But a phone in a
 * basement often says it is online when nothing gets through, so a request that
 * gets no answer at all counts as offline too, until the API answers again.
 *
 * While offline, TanStack Query pauses its requests: kept answers show, and a
 * screen with nothing kept says it needs a connection. Changes are not paused
 * (main.tsx makes them `networkMode: "always"`): one tried offline fails at once
 * with "Needs a connection.", and never waits to be sent later. Only the Play
 * View's taps wait (usePlay).
 */

/** What a request that got no answer at all fails with. */
export class OfflineError extends Error {
  constructor() {
    super("Needs a connection.");
    this.name = "OfflineError";
  }
}

const PROBE = 10_000;
let probing: number | undefined;

/** Ask the API whether it can be reached, every few seconds, until it answers. */
function probe() {
  if (probing !== undefined) return;
  const ask = async () => {
    if (!navigator.onLine) return; // the browser's online event will say when
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (response.ok) onlineManager.setOnline(true);
    } catch {
      // Still nothing.
    }
  };
  probing = window.setInterval(() => void ask(), PROBE);
  void ask();
}

/** As the app starts: offline if the browser says so. */
export function startConnection(): void {
  onlineManager.setOnline(typeof navigator === "undefined" ? true : navigator.onLine);
  onlineManager.subscribe((online) => {
    if (online && probing !== undefined) {
      window.clearInterval(probing);
      probing = undefined;
    }
  });
}

/** A request got no answer: offline until the API answers again. */
export function noAnswer(): void {
  if (onlineManager.isOnline()) onlineManager.setOnline(false);
  probe();
}

/** Whether a request failed for want of an answer, not because it was called off. */
export function isNoAnswer(error: unknown): boolean {
  return error instanceof OfflineError || (error instanceof TypeError && !(error instanceof DOMException));
}

/** Whether there is a connection, as `onlineManager` has it. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (changed) => onlineManager.subscribe(changed),
    () => onlineManager.isOnline(),
    () => true,
  );
}
