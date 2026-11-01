/**
 * The Scene view's pins: which of a troupe's characters are on a scene's page, in
 * the order they were added. Scenes are kept on the server (issue #231); what a
 * browser kept before that, one scene per troupe, is offered to be saved once.
 */

const key = (troupeId: string) => `horatio.scene.${troupeId}`;

/** The characters this browser kept for a troupe before scenes were on the server; none if it kept nothing. */
export function deviceScene(troupeId: string, storage: Storage | undefined = globalThis.localStorage): string[] {
  try {
    const raw = storage?.getItem(key(troupeId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? [...new Set(parsed.filter((id): id is string => typeof id === "string"))] : [];
  } catch {
    return [];
  }
}

/** Forget the browser's old scene for a troupe, once it is saved or dismissed. */
export function forgetDeviceScene(troupeId: string, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    storage?.removeItem(key(troupeId));
  } catch {
    // Storage that cannot be written cannot keep the old scene either.
  }
}

/** The scene with a character pinned at the end; as it was if already there. */
export function pin(ids: string[], characterId: string): string[] {
  return ids.includes(characterId) ? ids : [...ids, characterId];
}

export function unpin(ids: string[], characterId: string): string[] {
  return ids.filter((id) => id !== characterId);
}

/** Characters whose names have what was typed in them, those starting with it first. */
export function findPins<T extends { character_name: string }>(characters: T[], typed: string): T[] {
  const q = typed.trim().toLocaleLowerCase();
  if (!q) return characters;
  const named = characters.filter((c) => c.character_name.toLocaleLowerCase().includes(q));
  const starts = (c: T) => (c.character_name.toLocaleLowerCase().startsWith(q) ? 0 : 1);
  return [...named].sort((a, b) => starts(a) - starts(b));
}

/** The parts of a card that can be open; several at once. */
export type Section = "pools" | "powers" | "log" | "reset";

const openKey = (characterId: string) => `horatio.scene.open.${characterId}`;
const sections: readonly string[] = ["pools", "powers", "log", "reset"];

/** The sections left open on a character's card; none if the browser keeps nothing. */
export function loadOpen(characterId: string, storage: Storage | undefined = globalThis.localStorage): Section[] {
  try {
    const raw = storage?.getItem(openKey(characterId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((s): s is Section => sections.includes(s)) : [];
  } catch {
    return [];
  }
}

export function saveOpen(characterId: string, open: Section[], storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (open.length) storage?.setItem(openKey(characterId), JSON.stringify(open));
    else storage?.removeItem(openKey(characterId));
  } catch {
    // Private windows and full storage keep nothing; the card stays as it is in memory.
  }
}

/** The sections with one opened, or closed if it was open. */
export function toggleOpen(open: Section[], section: Section): Section[] {
  return open.includes(section) ? open.filter((s) => s !== section) : [...open, section];
}

/** What a card's turn order is worked out from: its initiative now, then the attributes that break a tie. */
export type Rank = { initiative: number; mental: number; physical: number; social: number };

/**
 * The pins in turn order (MET: VtM core p. 276; issue #371): the highest initiative
 * first, a tie going to the higher Mental, then Physical, then Social, and then to
 * whoever was put in the scene first. A card with no initiative yet, still loading
 * or a Stock NPC, which the book gives none, goes after them in the order they were added.
 */
export function byInitiative(ids: string[], ranks: Record<string, Rank | undefined>): string[] {
  const order = (r: Rank) => [r.initiative, r.mental, r.physical, r.social];
  return ids
    .map((id, at) => ({ id, at, rank: ranks[id] }))
    .sort((a, b) => {
      if (!a.rank || !b.rank) return Number(!a.rank) - Number(!b.rank) || a.at - b.at;
      const [x, y] = [order(a.rank), order(b.rank)];
      const first = x.findIndex((v, i) => v !== y[i]);
      return first < 0 ? a.at - b.at : y[first]! - x[first]!;
    })
    .map((p) => p.id);
}

const sortKey = "horatio.scene.sort";

/** Whether this device sorts scene cards by initiative; it stays as the storyteller left it. */
export function loadSorted(storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    return storage?.getItem(sortKey) === "initiative";
  } catch {
    return false;
  }
}

export function saveSorted(sorted: boolean, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (sorted) storage?.setItem(sortKey, "initiative");
    else storage?.removeItem(sortKey);
  } catch {
    // Kept for this visit only.
  }
}
