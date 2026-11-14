import { gameDate, placed, type ChronicleEvent } from "./chronicle";

/**
 * The story bible's chronology (#879): the chronicle's events (#711) as a list, those
 * with an in-game date in the order they happened in game, then those Horatio has no
 * in-game date for, in the order it recorded them.
 */

const day = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const gameDay = (iso: string) => day.format(gameDate(iso));
const realDay = (iso: string) => day.format(new Date(iso));

export type Entry = { event: ChronicleEvent; when: string };

/** When an event happened in game: a day, or a title's holding from one day to another. */
function inGame(e: ChronicleEvent): string {
  if (e.kind !== "title") return gameDay(e.on!);
  return `${gameDay(e.on!)} to ${e.ends_on ? gameDay(e.ends_on) : "now"}`;
}

/** When Horatio recorded it: a day, or a title's holding from one to another. */
function recorded(e: ChronicleEvent): string {
  if (e.kind !== "title") return realDay(e.at);
  return `${realDay(e.at)} to ${e.ends_at ? realDay(e.ends_at) : "now"}`;
}

export function chronology(events: readonly ChronicleEvent[]): {
  dated: Entry[];
  undated: Entry[];
} {
  const { shown, undated } = placed(events, true);
  // sort() is stable: events on the same day keep the server's order, as recorded.
  const dated = [...shown].sort((a, b) => a.from.getTime() - b.from.getTime()).map((p) => ({ event: p.event, when: inGame(p.event) }));
  return {
    dated,
    undated: undated.map((e) => ({ event: e, when: recorded(e) })),
  };
}
