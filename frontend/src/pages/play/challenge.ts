/**
 * A challenge thrown from a test pool (#698): the book's rules for what a rock,
 * paper, scissors test means for that pool (MET: VTM pp. 271–275). The phone throws
 * for this player only; what the other side showed is tapped in, since the phone
 * can't know it. Pure functions, so the rules are tested apart from the screen.
 */

import type { TestPool } from "../../api/types";
import { THROWS, type Throw } from "./throws";

/** Static: against a difficulty the Storyteller sets (p. 271). Opposed: against another character's pool (p. 273). */
export type Kind = "static" | "opposed";
/** Who is acting against whom in an opposed challenge (p. 273). */
export type Role = "attacker" | "defender";
export type Side = "me" | "them";
/** What a retest is made with: Willpower (pp. 272, 274), an overbid (p. 275), or a merit (p. 272). */
export type RetestBy = "willpower" | "overbid" | "merit";
export type Outcome = "win" | "tie" | "lose";

/** One rock, paper, scissors test: what each side showed, and the retest it was, if it was one. */
export type Test = { mine: Throw; theirs: Throw; retest: { by: RetestBy; side: Side } | null };

export type Challenge = {
  /** The pool it was thrown from, as it counted when loaded. */
  pool: { key: string; name: string; breakdown: string; unskilled: boolean };
  /** This player's test pool: the pool's total, changed here for a wild card the Storyteller gives. */
  mine: number;
  kind: Kind;
  /** In a static challenge the player is the one acting, as an attacker is. */
  role: Role;
  /** The opponent's test pool, or the difficulty: null until it is entered. */
  theirs: number | null;
  tests: Test[];
  /** A retest chosen and waiting for its throw. */
  next: { by: RetestBy; side: Side } | null;
  /** This player's throw, shown, waiting for what the other side showed. */
  pending: Throw | null;
  /** Who relented before a test (p. 275). */
  relented: Side | null;
};

/** The book's difficulty ratings for a static challenge (p. 272). */
export const DIFFICULTIES = [
  { name: "Easy", rating: 5 },
  { name: "Standard", rating: 8 },
  { name: "Difficult", rating: 15 },
  { name: "Challenging", rating: 20 },
  { name: "Epic", rating: 30 },
] as const;

const ATTRIBUTES = new Set(["Physical", "Social", "Mental"]);

/**
 * A challenge from a pool, as the Pools tab counts it now. Attacks and powers used
 * on someone are opposed with this character attacking; Dodge and resisting powers
 * are opposed with it defending; anything else (another skill, a discipline with no
 * one to resist it) starts as static, and the player can change either.
 */
export function load(pool: Pick<TestPool, "key" | "name" | "parts" | "versus">, total: number, breakdown: string): Challenge {
  const defends = pool.key === "dodge" || pool.key.startsWith("defense:");
  const attacks = pool.key.startsWith("attack:") || pool.key.startsWith("power:") || (pool.key.startsWith("discipline:") && !!pool.versus);
  return {
    pool: { key: pool.key, name: pool.name, breakdown, unskilled: unskilled(pool) },
    mine: total,
    kind: defends || attacks ? "opposed" : "static",
    role: defends ? "defender" : "attacker",
    theirs: defends || attacks ? null : 8,
    tests: [],
    next: null,
    pending: null,
    relented: null,
  };
}

/** A pool made with a skill the character hasn't got: a 0 in it that isn't an attribute (pp. 273, 275). */
export function unskilled(pool: Pick<TestPool, "parts">): boolean {
  return pool.parts.some((p) => !ATTRIBUTES.has(p.label) && p.value <= 0);
}

const BEATS: Record<Throw, Throw> = { rock: "scissors", scissors: "paper", paper: "rock" };

/** What a test's throws are for this player, before any pools are compared. */
export function outcome(mine: Throw, theirs: Throw): Outcome {
  if (mine === theirs) return "tie";
  return BEATS[mine] === theirs ? "win" : "lose";
}

/**
 * Who a tie goes to (pp. 272, 274): the one acting wins it only with a pool greater
 * than the difficulty or the defender's, so a defender wins it with an equal one.
 */
export function tieGoesTo(c: Pick<Challenge, "kind" | "role" | "mine" | "theirs">): Side | null {
  if (c.theirs === null) return null;
  if (c.kind === "opposed" && c.role === "defender") return c.mine >= c.theirs ? "me" : "them";
  return c.mine > c.theirs ? "me" : "them";
}

/** Who prevails in one test: the winner of the throw, or on a tie, by the pools. */
export function prevails(c: Pick<Challenge, "kind" | "role" | "mine" | "theirs">, test: Pick<Test, "mine" | "theirs">): Side | null {
  const o = outcome(test.mine, test.theirs);
  if (o === "win") return "me";
  if (o === "lose") return "them";
  return tieGoesTo(c);
}

/**
 * An overbid (p. 275): a pool at least double the opponent's gains a free retest, in
 * an opposed challenge. A pool of nothing doubles nothing, so it needs one above 0.
 */
export function overbids(c: Pick<Challenge, "kind" | "mine" | "theirs">, side: Side): boolean {
  if (c.kind !== "opposed" || c.theirs === null) return false;
  const [own, other] = side === "me" ? [c.mine, c.theirs] : [c.theirs, c.mine];
  return own > 0 && own >= 2 * other;
}

/** A static challenge the Storyteller may let succeed without a test: a pool at least double the difficulty (p. 273). */
export function automatic(c: Pick<Challenge, "kind" | "mine" | "theirs">): boolean {
  return c.kind === "static" && c.theirs !== null && c.theirs > 0 && c.mine >= 2 * c.theirs;
}

/** Whether this player can score an exceptional success at all: only the one acting, with the greater pool (pp. 272, 274). */
export function canBeExceptional(c: Pick<Challenge, "kind" | "role" | "mine" | "theirs">): boolean {
  return (c.kind === "static" || c.role === "attacker") && c.theirs !== null && c.mine > c.theirs;
}

/**
 * The retests open now, to the loser of the latest test. Only the loser may retest
 * (p. 274); the target of a static challenge has no Willpower, so only the player
 * retests one (p. 272). Never more than one Willpower retest in a challenge, by
 * either side; an overbid's free retest is an exception to that, usable before or
 * after it (pp. 272–273, 275). A merit's retest is the player's to say: one a side.
 */
export function retests(c: Challenge): { by: RetestBy; side: Side }[] {
  const last = c.tests.at(-1);
  if (!last || c.relented || c.next) return [];
  const winner = prevails(c, last);
  if (winner === null) return [];
  const loser: Side = winner === "me" ? "them" : "me";
  if (c.kind === "static" && loser === "them") return [];
  const used = (by: RetestBy, side?: Side) => c.tests.some((t) => t.retest?.by === by && (side === undefined || t.retest.side === side));
  const open: { by: RetestBy; side: Side }[] = [];
  if (!used("willpower")) open.push({ by: "willpower", side: loser });
  if (overbids(c, loser) && !used("overbid", loser)) open.push({ by: "overbid", side: loser });
  if (!used("merit", loser)) open.push({ by: "merit", side: loser });
  return open;
}

export type Result = {
  /** This player prevails. */
  won: boolean;
  /** This player scores an exceptional success. */
  exceptional: boolean;
  /** The other side does: they acted against this player and won every test outright with the greater pool. */
  theirExceptional: boolean;
  /** Lost the test outright with a pool needing a skill the character hasn't got (pp. 273, 275). */
  critical: boolean;
  /** No Willpower or overbid retest is open: the result stands, unless someone has a merit that retests. */
  final: boolean;
};

/**
 * The challenge's result so far, from the latest test. Exceptional success needs
 * the one acting to have won every test in the challenge outright, retests and all,
 * with the greater pool; a tie or a lost test along the way makes it a normal
 * success (pp. 272, 274). Relenting loses at once, and the one acting scores an
 * exceptional success if the one who relented had the smaller pool (p. 275).
 */
export function result(c: Challenge): Result | null {
  if (c.theirs === null) return null;
  const acting = c.kind === "static" || c.role === "attacker";
  if (c.relented) {
    const won = c.relented === "them";
    // Relenting gives the one acting against the relenter an exceptional success if the relenter's pool is the smaller.
    const relenterPool = c.relented === "me" ? c.mine : c.theirs;
    const winnerPool = c.relented === "me" ? c.theirs : c.mine;
    const winnerActs = won ? acting : c.kind === "opposed" && !acting;
    const exceptional = winnerActs && relenterPool < winnerPool;
    return { won, exceptional: won && exceptional, theirExceptional: !won && exceptional, critical: false, final: true };
  }
  const last = c.tests.at(-1);
  if (!last) return null;
  const won = prevails(c, last) === "me";
  const allMine = c.tests.every((t) => outcome(t.mine, t.theirs) === "win");
  const allTheirs = c.tests.every((t) => outcome(t.mine, t.theirs) === "lose");
  return {
    won,
    exceptional: won && acting && allMine && c.mine > c.theirs,
    theirExceptional: !won && c.kind === "opposed" && !acting && allTheirs && c.theirs > c.mine,
    critical: !won && acting && c.pool.unskilled && outcome(last.mine, last.theirs) === "lose",
    final: !c.next && retests(c).every((r) => r.by === "merit"),
  };
}

/** A test recorded: what the other side showed against this player's pending throw. */
export function record(c: Challenge, theirs: Throw): Challenge {
  if (!c.pending) return c;
  return { ...c, tests: [...c.tests, { mine: c.pending, theirs, retest: c.next }], next: null, pending: null };
}

/** Whether a throw now is part of the challenge: before the first test, or for a retest chosen. */
export function expecting(c: Challenge): boolean {
  return c.theirs !== null && !c.relented && (c.tests.length === 0 || c.next !== null);
}

/** The same challenge again from the start: its pool and the other side kept. */
export function restart(c: Challenge): Challenge {
  return { ...c, tests: [], next: null, pending: null, relented: null };
}

/** A challenge kept for this browser tab, read safely: storage can be blocked, empty or hold something else. */
export function readChallenge(raw: string | null): Challenge | null {
  try {
    const c = JSON.parse(raw ?? "null") as Challenge | null;
    if (!c || typeof c !== "object" || typeof c.mine !== "number" || !Array.isArray(c.tests) || !c.pool || typeof c.pool.name !== "string") return null;
    if (!["static", "opposed"].includes(c.kind) || !["attacker", "defender"].includes(c.role)) return null;
    const isThrow = (t: unknown) => THROWS.includes(t as Throw);
    if (!c.tests.every((t) => isThrow(t.mine) && isThrow(t.theirs))) return null;
    return { ...c, pending: isThrow(c.pending) ? c.pending : null };
  } catch {
    return null;
  }
}

const RETEST_NAMES: Record<RetestBy, string> = { willpower: "Willpower", overbid: "overbid", merit: "a merit" };

/** "Retest with Willpower", "Their overbid retest": a retest's name, for its button and the list of tests. */
export function retestName(r: { by: RetestBy; side: Side }): string {
  if (r.by === "overbid") return r.side === "me" ? "Overbid retest" : "Their overbid retest";
  return r.side === "me" ? `Retest with ${RETEST_NAMES[r.by]}` : `They retest with ${RETEST_NAMES[r.by]}`;
}

/** What a tie means now, said before throwing. */
export function tieNote(c: Challenge): string | null {
  const to = tieGoesTo(c);
  if (to === null || c.theirs === null) return null;
  const against = c.kind === "static" ? `the difficulty, ${c.theirs}` : `their ${c.theirs}`;
  if (to === "me") return c.mine > c.theirs ? `A tie goes to you: your ${c.mine} is greater than ${against}.` : `A tie goes to you: you defend, and your ${c.mine} is at least their ${c.theirs}.`;
  return c.kind === "opposed" && c.role === "defender" ? `A tie goes to them: their ${c.theirs} is greater than your ${c.mine}.` : `A tie goes against you: your ${c.mine} isn't greater than ${against}.`;
}

/** The result in words: "Exceptional success", "You win the challenge", "You lose: they score an exceptional success". */
export function resultText(c: Challenge, r: Result): string {
  const acting = c.kind === "static" || c.role === "attacker";
  if (r.won) {
    if (r.exceptional) return "Exceptional success";
    return acting ? "Success" : "You win: their action fails";
  }
  if (r.theirExceptional) return "You lose: they score an exceptional success";
  return acting ? "Failure" : "You lose: their action succeeds";
}
