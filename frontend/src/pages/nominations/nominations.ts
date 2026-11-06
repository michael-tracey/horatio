/**
 * Player Nominations (#470) as players read them: each month in the order fixed as
 * it was published, and the starred ones rotating in the footer of the troupe's
 * pages.
 */

/**
 * A month's nominations in their published order. The server shuffles each once,
 * as it is published, and keeps its place (`order`); this keeps to that whatever
 * order they arrive in, so a visit, a refetch or a later "Publish more" never
 * reshuffles what is there.
 */
export function monthOrder<T extends { id: string; order: number }>(entries: readonly T[]): T[] {
  return [...entries].sort((a, b) => a.order - b.order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/** How long each starred nomination stays in the footer before the next. */
export const ROTATE_MS = 12_000;

/** Where the footer starts: somewhere new on each page load, so every one has its turn. */
export function firstShown(count: number, random: () => number = Math.random): number {
  return count > 0 ? Math.min(count - 1, Math.floor(random() * count)) : 0;
}

/** The one after, round again after the last. */
export function nextShown(at: number, count: number): number {
  return count > 0 ? (at + 1) % count : 0;
}

/** Whether the footer turns by itself: not while paused, nor for someone who asks for less motion, nor with one alone. */
export function rotates(count: number, paused: boolean, reducedMotion: boolean): boolean {
  return count > 1 && !paused && !reducedMotion;
}

/** The start of a nomination, to name it by: its first few words. */
export function excerpt(text: string, most = 40): string {
  const line = text.split(/\s+/).join(" ").trim();
  return line.length <= most ? line : `${line.slice(0, most - 1).trimEnd()}…`;
}

/**
 * What a cycle's one Publish publishes, by the troupe's settings (#471): its Player
 * Nominations, its Remembrances, or both, for the tab's title, the button and the
 * count.
 */
export function publishedWhat(nominations: boolean, remembrances: boolean) {
  if (nominations && remembrances)
    return { title: "Nominations and remembrances", button: "Publish nominations and remembrances", one: "entry", many: "entries" };
  if (remembrances) return { title: "Remembrances", button: "Publish remembrances", one: "memory", many: "memories" };
  return { title: "Player Nominations", button: "Publish nominations", one: "nomination", many: "nominations" };
}
