import { useCallback, useSyncExternalStore } from "react";

/**
 * Which downtime results a player has seen, for the count on the Results tab.
 * Horatio keeps no record of it, so each device remembers the newest result
 * shown on the Results tab, per character; a result delivered after it is new.
 * The times are the server's, so a device's own clock never moves the count.
 */

const key = (characterId: string) => `horatio.results-seen.${characterId}`;

/** Without a record on this device, a result counts as new for this long after it is delivered. */
export const NEW_FOR_MS = 30 * 24 * 60 * 60 * 1000;

const listeners = new Set<() => void>();

/** The newest delivery the Results tab has shown on this device, or null. */
export function seenUpTo(characterId: string, storage: Storage | undefined = globalThis.localStorage): string | null {
  try {
    return storage?.getItem(key(characterId)) ?? null;
  } catch {
    return null;
  }
}

/** Remember that the Results tab has shown everything delivered up to `deliveredAt`. */
export function markSeen(characterId: string, deliveredAt: string, storage: Storage | undefined = globalThis.localStorage): void {
  const seen = seenUpTo(characterId, storage);
  if (seen && Date.parse(seen) >= Date.parse(deliveredAt)) return;
  try {
    storage?.setItem(key(characterId), deliveredAt);
  } catch {
    // Storage that cannot be written leaves the count as it was.
  }
  for (const listener of listeners) listener();
}

/** Whether a delivery is new to the player: after the newest they have seen here, or
 * without a record on this device, delivered lately. */
export function isNew(delivered: string, seen: string | null, now: number = Date.now()): boolean {
  return Date.parse(delivered) > (seen ? Date.parse(seen) : now - NEW_FOR_MS);
}

/** How many of the deliveries (one time per cycle) are new to the player. */
export function newResults(delivered: string[], seen: string | null, now: number = Date.now()): number {
  return delivered.filter((d) => isNew(d, seen, now)).length;
}

/** `seenUpTo`, kept up to date as the Results tab marks results seen. */
export function useSeenUpTo(characterId: string): string | null {
  const subscribe = useCallback((listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, []);
  return useSyncExternalStore(subscribe, () => seenUpTo(characterId));
}
