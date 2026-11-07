import type { QueryKey } from "@tanstack/react-query";
import type { CharacterListOut } from "../api/types";

/**
 * What Horatio keeps on a device for a game with no signal (#502), and whose it is.
 *
 * A person chooses, on each device, whether their characters are kept there
 * ("Keep my characters on this device"). Kept, the answers the app has for their
 * own active characters (the sheet, the Play View, its reference and powers), the
 * rules those need, and who they are, are stored under their own key, so one
 * person's never shows for another. Staff screens and other players' characters
 * are never kept, whoever the person is. Signing out clears it all.
 */

export type Keeping = "on" | "off";

const SETTING = "horatio.offline.keep.";
/** The device has asked its question once (KeepQuestion), whoever answered. */
const ASKED = "horatio.offline.asked";
/** Whose kept answers to load when the app opens, before it can ask who is signed in. */
const WHO = "horatio.offline.who";

function read(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(storage: Storage | undefined, key: string, value: string | null): void {
  try {
    if (value === null) storage?.removeItem(key);
    else storage?.setItem(key, value);
  } catch {
    // A private window keeps nothing: the setting lasts as long as the page.
  }
}

/** This person's choice on this device, or null before they have made one (it is off until then). */
export function keeping(userId: string, storage: Storage | undefined = globalThis.localStorage): Keeping | null {
  const value = read(storage, SETTING + userId);
  return value === "on" || value === "off" ? value : null;
}

export function setKeeping(userId: string, value: Keeping | null, storage: Storage | undefined = globalThis.localStorage): void {
  write(storage, SETTING + userId, value);
}

export function wasAsked(storage: Storage | undefined = globalThis.localStorage): boolean {
  return read(storage, ASKED) === "1";
}

export function markAsked(storage: Storage | undefined = globalThis.localStorage): void {
  write(storage, ASKED, "1");
}

/** The person whose kept answers the app loads as it opens, if they keep them here. */
export function keptFor(storage: Storage | undefined = globalThis.localStorage): string | null {
  const who = read(storage, WHO);
  return who && keeping(who, storage) === "on" ? who : null;
}

export function setKeptFor(userId: string | null, storage: Storage | undefined = globalThis.localStorage): void {
  write(storage, WHO, userId);
}

/** The key a person's kept answers are stored under, in IndexedDB. */
export function recordKey(userId: string): string {
  return `person:${userId}`;
}

/** The characters kept for a person: their own player characters in play, not retired or still being made. */
export function keptCharacters(list: CharacterListOut[] | undefined, userId: string): CharacterListOut[] {
  return (list ?? []).filter((c) => c.player_id === userId && c.kind === "pc" && c.status !== "retired" && c.creation_complete);
}

/** What a person's kept answers may hold: their kept characters, and those characters' troupes. */
export type Mine = { characters: Set<string>; troupes: Set<string> };

export function mineOf(list: CharacterListOut[] | undefined, userId: string): Mine {
  const kept = keptCharacters(list, userId);
  return {
    characters: new Set(kept.map((c) => c.id)),
    troupes: new Set(kept.flatMap((c) => [c.home_troupe_id, c.building_troupe_id].filter((t): t is string => !!t))),
  };
}

/** Who the person is, their characters and troupes: about them alone. */
const PERSON = new Set(["me", "characters", "troupes"]);
/** The rules: the same for everyone. */
const RULES = new Set(["catalogue", "splats"]);
/** About one character, named second in the key: kept for the person's own. The sheet and
 * what it shows, and the Play View and its tabs. Never the Play View's Others tab, which
 * is about other characters, nor anything between games (downtimes, XP, results). */
const CHARACTER = new Set([
  "character",
  "sheet",
  "play",
  "play-reference",
  "play-games",
  "character-equipment",
  "teaching",
  "power-choices",
  "retainers",
  "specializations",
  "identities",
  "status",
  "character-titles",
  "character-shared",
  "held-locations",
  "character-locations",
  "domitor",
  "picture",
]);

/** Whether a query's answer is kept on the device for the person whose `mine` it is. */
export function keepsQuery(key: QueryKey, mine: Mine): boolean {
  const [what, of] = key;
  if (typeof what !== "string") return false;
  if (PERSON.has(what) || RULES.has(what)) return true;
  if (what === "troupe") return typeof of === "string" && mine.troupes.has(of);
  if (CHARACTER.has(what)) return typeof of === "string" && mine.characters.has(of);
  return false;
}

/** Taps waiting to be sent are kept as `horatio.play.<character id>` (play/tracker.ts). */
const QUEUE = /^horatio\.play\.[0-9a-f-]{36}$/;
/** What else the Play View has kept about a character on the device: its reference and
 * equipment (before #502), the modifiers set on it, and a feeding under way. */
const CHARACTER_DATA = /^horatio\.(play\.(reference|equipment|modifiers)\.|feed\.[0-9a-f-]{36}$)/;

function keysOf(storage: Storage | undefined): string[] {
  try {
    return storage ? Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter((k): k is string => k !== null) : [];
  } catch {
    return [];
  }
}

/** The taps waiting on this device, by character, as the Play View keeps them. */
export function waitingTaps(storage: Storage | undefined = globalThis.localStorage): { characterId: string; taps: { id: string }[] }[] {
  return keysOf(storage)
    .filter((k) => QUEUE.test(k))
    .flatMap((k) => {
      try {
        const parsed: unknown = JSON.parse(storage?.getItem(k) ?? "[]");
        const taps = Array.isArray(parsed) ? (parsed as { id: string }[]).filter((t) => t && typeof t.id === "string") : [];
        return taps.length ? [{ characterId: k.slice("horatio.play.".length), taps }] : [];
      } catch {
        return [];
      }
    });
}

/** Taps the server has, gone from what waits on the device; any made since stay. */
export function dropSent(characterId: string, sent: string[], storage: Storage | undefined = globalThis.localStorage): void {
  const key = `horatio.play.${characterId}`;
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(key) ?? "[]");
    const left = Array.isArray(parsed) ? parsed.filter((t: { id?: string }) => !sent.includes(t?.id ?? "")) : [];
    write(storage, key, left.length ? JSON.stringify(left) : null);
  } catch {
    // Nothing readable there.
  }
}

/** How many taps are waiting on this device to be sent, for every character. */
export function tapsWaiting(storage: Storage | undefined = globalThis.localStorage): number {
  return waitingTaps(storage).reduce((n, q) => n + q.taps.length, 0);
}

/** At sign-out: the taps waiting and anything kept about a character go, and the app
 * loads no one's answers as it opens. The person's choice stays, so signing in again
 * on their own phone keeps their characters again; it holds nothing about them. */
export function clearDevice(storage: Storage | undefined = globalThis.localStorage): void {
  for (const key of keysOf(storage)) if (QUEUE.test(key) || CHARACTER_DATA.test(key)) write(storage, key, null);
  setKeptFor(null, storage);
}
