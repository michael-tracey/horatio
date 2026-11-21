import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether a player's sheet shows its −, +, Add and × on a phone: Make changes
 * turns them on, Done turns them off (#1055). Each device remembers it per
 * character, across visits and reloads (#1115). Without storage it lasts for
 * this visit.
 */

const key = (characterId: string) => `horatio.sheet-changing.${characterId}`;

/** Whether Make changes was left on for a character on this device. */
export function loadChanging(characterId: string, storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    return storage?.getItem(key(characterId)) === "1";
  } catch {
    return false;
  }
}

/** Remember Make changes on or off for a character on this device. */
export function saveChanging(characterId: string, on: boolean, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (on) storage?.setItem(key(characterId), "1");
    else storage?.removeItem(key(characterId));
  } catch {
    // Storage that cannot be written keeps it for this visit only.
  }
}

// This visit's choices, read from storage the first time each is asked for.
const choices = new Map<string, boolean>();
const listeners = new Set<() => void>();

function changing(characterId: string): boolean {
  let on = choices.get(characterId);
  if (on === undefined) {
    on = loadChanging(characterId);
    choices.set(characterId, on);
  }
  return on;
}

/** Whether Make changes is on for a character, and a way to turn it on or off. */
export function useChanging(characterId: string): [boolean, (on: boolean) => void] {
  const subscribe = useCallback((listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, []);
  const on = useSyncExternalStore(subscribe, () => changing(characterId));
  const set = useCallback(
    (next: boolean) => {
      if (changing(characterId) === next) return;
      choices.set(characterId, next);
      saveChanging(characterId, next);
      for (const listener of listeners) listener();
    },
    [characterId],
  );
  return [on, set];
}
