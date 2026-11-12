import { describe, expect, it } from "vitest";
import {
  automatic,
  canBeExceptional,
  expecting,
  load,
  outcome,
  overbids,
  prevails,
  readChallenge,
  record,
  restart,
  result,
  retests,
  tieGoesTo,
  tieNote,
  unskilled,
  type Challenge,
  type RetestBy,
  type Side,
} from "./challenge";
import type { Throw } from "./throws";

const pool = (key: string, parts: { label: string; value: number }[] = [{ label: "Physical", value: 5 }, { label: "Brawl", value: 3 }], versus: string | null = null) => ({
  key,
  name: key,
  parts,
  versus,
});

function challenge(over: Partial<Challenge> = {}): Challenge {
  return { ...load(pool("attack:Brawl"), 12, "Physical 5 + Brawl 3"), theirs: 6, ...over };
}

/** Throws a test: this player shows `mine`, the other side `theirs`, as a retest if one was chosen. */
function test(c: Challenge, mine: Throw, theirs: Throw): Challenge {
  return record({ ...c, pending: mine }, theirs);
}

function retest(c: Challenge, by: RetestBy, side: Side): Challenge {
  expect(retests(c)).toContainEqual({ by, side });
  return { ...c, next: { by, side } };
}

describe("a pool loaded for a challenge", () => {
  it("is opposed and attacking for an attack, a power test, or a discipline used on someone", () => {
    for (const p of [pool("attack:Brawl"), pool("power:Psychic Assault"), pool("discipline:Dominate", [], "Mental + Willpower")]) {
      const c = load(p, 9, "");
      expect([c.kind, c.role, c.theirs]).toEqual(["opposed", "attacker", null]);
    }
  });

  it("is opposed and defending for Dodge and resisting powers", () => {
    for (const p of [pool("dodge"), pool("defense:Mental", [{ label: "Mental", value: 4 }])]) {
      const c = load(p, 9, "");
      expect([c.kind, c.role]).toEqual(["opposed", "defender"]);
    }
  });

  it("is static, at Standard difficulty, for another skill", () => {
    const c = load(pool("skill:Security", [{ label: "Physical", value: 3 }, { label: "Security", value: 5 }]), 9, "");
    expect([c.kind, c.theirs]).toEqual(["static", 8]);
  });

  it("is unskilled when a skill in it is 0, not for an attribute alone", () => {
    expect(unskilled(pool("attack:Brawl", [{ label: "Physical", value: 5 }, { label: "Brawl", value: 0 }]))).toBe(true);
    expect(unskilled(pool("defense:Social", [{ label: "Social", value: 0 }]))).toBe(false);
    expect(unskilled(pool("attack:Brawl"))).toBe(false);
  });
});

describe("a single test", () => {
  it("rock beats scissors, scissors beat paper, paper beats rock", () => {
    expect(outcome("rock", "scissors")).toBe("win");
    expect(outcome("scissors", "paper")).toBe("win");
    expect(outcome("paper", "rock")).toBe("win");
    expect(outcome("rock", "paper")).toBe("lose");
    expect(outcome("paper", "paper")).toBe("tie");
  });

  it("gives a tie to the one acting only with the greater pool (pp. 272, 274)", () => {
    expect(tieGoesTo({ kind: "opposed", role: "attacker", mine: 12, theirs: 6 })).toBe("me");
    expect(tieGoesTo({ kind: "opposed", role: "attacker", mine: 6, theirs: 6 })).toBe("them");
    expect(tieGoesTo({ kind: "static", role: "attacker", mine: 9, theirs: 8 })).toBe("me");
    expect(tieGoesTo({ kind: "static", role: "attacker", mine: 8, theirs: 8 })).toBe("them");
  });

  it("gives a defender the tie with an equal pool", () => {
    expect(tieGoesTo({ kind: "opposed", role: "defender", mine: 6, theirs: 6 })).toBe("me");
    expect(tieGoesTo({ kind: "opposed", role: "defender", mine: 6, theirs: 12 })).toBe("them");
    expect(prevails({ kind: "opposed", role: "defender", mine: 6, theirs: 6 }, { mine: "rock", theirs: "rock" })).toBe("me");
  });

  it("says what a tie means before throwing", () => {
    expect(tieNote(challenge())).toBe("A tie goes to you: your 12 is greater than their 6.");
    expect(tieNote(challenge({ mine: 6, theirs: 6 }))).toBe("A tie goes against you: your 6 isn't greater than their 6.");
    expect(tieNote(challenge({ kind: "static", mine: 9, theirs: 8 }))).toBe("A tie goes to you: your 9 is greater than the difficulty, 8.");
  });
});

describe("overbids and automatic success", () => {
  it("overbids at exactly double the opponent's pool, not below (p. 275)", () => {
    expect(overbids(challenge({ mine: 12, theirs: 6 }), "me")).toBe(true);
    expect(overbids(challenge({ mine: 11, theirs: 6 }), "me")).toBe(false);
    expect(overbids(challenge({ mine: 6, theirs: 12 }), "them")).toBe(true);
    expect(overbids(challenge({ mine: 0, theirs: 0 }), "me")).toBe(false);
  });

  it("never overbids in a static challenge, which may succeed at double the difficulty instead (p. 273)", () => {
    const c = challenge({ kind: "static", mine: 16, theirs: 8 });
    expect(overbids(c, "me")).toBe(false);
    expect(automatic(c)).toBe(true);
    expect(automatic({ ...c, mine: 15 })).toBe(false);
    expect(automatic(challenge({ mine: 16, theirs: 8 }))).toBe(false);
  });
});

describe("exceptional success", () => {
  it("is possible only for the one acting, with the greater pool", () => {
    expect(canBeExceptional(challenge())).toBe(true);
    expect(canBeExceptional(challenge({ mine: 6 }))).toBe(false);
    expect(canBeExceptional(challenge({ role: "defender" }))).toBe(false);
  });

  it("comes from winning the first test outright with the greater pool", () => {
    const r = result(test(challenge(), "rock", "scissors"));
    // So far: they can still spend Willpower to retest.
    expect(r).toMatchObject({ won: true, exceptional: true, final: false });
  });

  it("is a normal success after a tie won on pools", () => {
    expect(result(test(challenge(), "rock", "rock"))).toMatchObject({ won: true, exceptional: false });
  });

  it("is a normal success with a pool no greater than theirs", () => {
    expect(result(test(challenge({ mine: 6 }), "rock", "scissors"))).toMatchObject({ won: true, exceptional: false });
  });

  it("is lost if any retest was lost or tied, even when the challenge is won", () => {
    // Won, they retest with Willpower and win, then the overbid retest is won: not every test was won.
    let c = test(challenge(), "rock", "scissors");
    c = test(retest(c, "willpower", "them"), "rock", "paper");
    c = test(retest(c, "overbid", "me"), "paper", "rock");
    expect(result(c)).toMatchObject({ won: true, exceptional: false, final: true });
  });

  it("is theirs when they act against this player and win every test outright with the greater pool", () => {
    const c = test(challenge({ role: "defender", mine: 6, theirs: 12 }), "rock", "paper");
    expect(result(c)).toMatchObject({ won: false, theirExceptional: true });
  });
});

describe("retests", () => {
  it("are open only to the loser of the latest test", () => {
    const won = test(challenge(), "rock", "scissors");
    expect(retests(won).every((r) => r.side === "them")).toBe(true);
    const lost = test(challenge(), "rock", "paper");
    expect(retests(lost).every((r) => r.side === "me")).toBe(true);
  });

  it("allow one Willpower retest a challenge, by either side", () => {
    let c = test(challenge({ mine: 7, theirs: 6 }), "rock", "paper");
    c = test(retest(c, "willpower", "me"), "rock", "scissors");
    expect(retests(c).some((r) => r.by === "willpower")).toBe(false);
    // Only a merit could retest it now, which is the player's to say.
    expect(result(c)?.final).toBe(true);
  });

  it("take an overbid before or after Willpower", () => {
    // Overbid first, then Willpower.
    let c = test(challenge(), "rock", "paper");
    c = test(retest(c, "overbid", "me"), "rock", "paper");
    c = test(retest(c, "willpower", "me"), "paper", "rock");
    expect(result(c)?.won).toBe(true);
    // Willpower first, then the overbid.
    let d = test(challenge(), "rock", "paper");
    d = test(retest(d, "willpower", "me"), "rock", "paper");
    d = test(retest(d, "overbid", "me"), "paper", "rock");
    expect(result(d)?.won).toBe(true);
  });

  it("follow the book's example: the hunter overbids after Vincent's Willpower retest (p. 275)", () => {
    // Vincent defends with 6 against the hunter's 12: a tie goes to the hunter.
    let c = test(challenge({ role: "defender", mine: 6, theirs: 12 }), "rock", "rock");
    expect(result(c)?.won).toBe(false);
    c = test(retest(c, "willpower", "me"), "paper", "rock");
    expect(result(c)?.won).toBe(true);
    c = test(retest(c, "overbid", "them"), "rock", "paper");
    expect(result(c)).toMatchObject({ won: false, theirExceptional: false });
  });

  it("in a static challenge are the player's alone: the target has no Willpower (p. 272)", () => {
    const won = test(challenge({ kind: "static", theirs: 8 }), "rock", "scissors");
    expect(retests(won)).toEqual([]);
    const lost = test(challenge({ kind: "static", theirs: 8 }), "rock", "paper");
    expect(retests(lost).map((r) => r.by)).toEqual(["willpower", "merit"]);
  });

  it("follow the book's static example: Vincent's 9 wins a tie on the retest against 8 (p. 273)", () => {
    let c = test(challenge({ kind: "static", mine: 9, theirs: 8 }), "scissors", "rock");
    c = test(retest(c, "willpower", "me"), "paper", "paper");
    expect(result(c)).toMatchObject({ won: true, exceptional: false });
  });

  it("allow a merit's retest once a side", () => {
    let c = test(challenge({ mine: 7 }), "rock", "paper");
    c = test(retest(c, "merit", "me"), "rock", "paper");
    expect(retests(c).some((r) => r.by === "merit")).toBe(false);
  });

  it("wait for the throw once one is chosen", () => {
    const c = retest(test(challenge(), "rock", "paper"), "willpower", "me");
    expect(expecting(c)).toBe(true);
    expect(retests(c)).toEqual([]);
    expect(result(c)?.final).toBe(false);
  });
});

describe("critical failure", () => {
  const brawl0 = () => ({ ...load(pool("attack:Brawl", [{ label: "Physical", value: 5 }, { label: "Brawl", value: 0 }]), 5, ""), theirs: 6 });

  it("comes from losing the test without the skill (pp. 273, 275)", () => {
    expect(result(test(brawl0(), "rock", "paper"))?.critical).toBe(true);
  });

  it("doesn't come from a tie, even one lost on pools", () => {
    expect(result(test(brawl0(), "rock", "rock"))).toMatchObject({ won: false, critical: false });
  });

  it("doesn't come with the skill", () => {
    expect(result(test(challenge({ mine: 5 }), "rock", "paper"))?.critical).toBe(false);
  });
});

describe("relenting (p. 275)", () => {
  it("loses at once, and the attacker scores an exceptional success over a smaller pool", () => {
    expect(result(challenge({ role: "defender", mine: 6, theirs: 12, relented: "me" }))).toMatchObject({ won: false, theirExceptional: true, final: true });
    expect(result(challenge({ role: "defender", mine: 12, theirs: 12, relented: "me" }))).toMatchObject({ won: false, theirExceptional: false });
  });

  it("wins for this player when they relent, exceptionally if this player attacks with the greater pool", () => {
    expect(result(challenge({ relented: "them" }))).toMatchObject({ won: true, exceptional: true });
    expect(result(challenge({ role: "defender", mine: 12, relented: "them" }))).toMatchObject({ won: true, exceptional: false });
  });
});

describe("kept for the browser tab", () => {
  it("reads back what it kept, and nothing from junk", () => {
    const c = test(challenge(), "rock", "scissors");
    expect(readChallenge(JSON.stringify(c))).toEqual(c);
    expect(readChallenge("not json")).toBeNull();
    expect(readChallenge(null)).toBeNull();
    expect(readChallenge(JSON.stringify({ ...c, tests: [{ mine: "lizard", theirs: "rock" }] }))).toBeNull();
  });

  it("starts again with the pool and the other side kept", () => {
    const c = restart(test(challenge(), "rock", "scissors"));
    expect([c.tests, c.theirs, c.mine]).toEqual([[], 6, 12]);
  });
});
