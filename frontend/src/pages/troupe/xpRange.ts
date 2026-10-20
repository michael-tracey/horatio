/** A troupe's XP floor and ceiling in words, and what joining does to a
 * character's XP (issue #74), apart from the screens so they can be tested. */

type Range = {
  starting_xp: number;
  floor: number;
  ceiling: number;
  games: number;
  game_xp: number;
  downtimes: number;
  downtime_xp: number;
  set_floor: number;
  set_ceiling: number;
};

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** What makes up each figure: "30 starting + 96 from 12 games − 10 set by hand". */
export function makeUp(r: Range): { floor: string; ceiling: string } {
  const games: [number, string] | null = r.games ? [r.game_xp, `from ${plural(r.games, "game")}`] : null;
  const downtimes: [number, string] | null = r.downtimes ? [r.downtime_xp, `from ${plural(r.downtimes, "downtime")}`] : null;
  const said = (parts: ([number, string] | null)[]) =>
    parts.reduce(
      (text, part) => (part && part[0] ? `${text} ${part[0] < 0 ? "−" : "+"} ${Math.abs(part[0])} ${part[1]}` : text),
      `${r.starting_xp} starting`,
    );
  return {
    floor: said([games, [r.set_floor, "set by hand"]]),
    ceiling: said([games, downtimes, [r.set_ceiling, "set by hand"]]),
  };
}

type Review = { given: number; self_entered: number; floor: number; ceiling: number; top_up_asked: boolean };
export type XpChoice = { self_entered: "keep" | "remove"; top_up: boolean | null; above_ceiling: "keep" | "remove"; extra: number };

/** Mirrors horatio.xp_range.plan: self-entered XP goes first, so the floor and
 * ceiling are measured against what the character keeps. */
export function joining(r: Review, choice: XpChoice) {
  const removed = choice.self_entered === "remove" ? r.self_entered : 0;
  const given = r.given - removed;
  const topUp = choice.top_up ?? r.top_up_asked;
  const below = Math.max(0, r.floor - given);
  const above = Math.max(0, given - r.ceiling);
  const toppedUp = topUp ? below : 0;
  const capped = choice.above_ceiling === "remove" ? above : 0;
  return { given, below, above, removed, toppedUp, capped, after: given + toppedUp - capped + choice.extra };
}
