import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button, Input, Select } from "../../components/ui";
import {
  automatic,
  canBeExceptional,
  DIFFICULTIES,
  expecting,
  outcome,
  overbids,
  prevails,
  readChallenge,
  record,
  restart,
  result,
  resultText,
  retestName,
  retests,
  tieNote,
  type Challenge,
  type RetestBy,
  type Side,
} from "./challenge";
import type { ThrowImages } from "./throwImages";
import { THROW_NAMES, THROWS } from "./throws";

/** Where this browser tab keeps the challenge, so going to the Tracker and back keeps it. */
const KEY = "horatio.challenge";

function keptStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export type Challenging = {
  challenge: Challenge | null;
  /** Change the challenge, from what it is now; null clears it. */
  update: (next: (c: Challenge | null) => Challenge | null) => void;
};

/** The challenge being thrown, kept for this browser tab only: like every throw, it goes nowhere. */
export function useChallenge(storage: Storage | null = keptStorage()): Challenging {
  const [challenge, setChallenge] = useState<Challenge | null>(() => {
    try {
      return readChallenge(storage?.getItem(KEY) ?? null);
    } catch {
      return null;
    }
  });
  useEffect(() => {
    try {
      if (challenge) storage?.setItem(KEY, JSON.stringify(challenge));
      else storage?.removeItem(KEY);
    } catch {
      // Kept for this visit only.
    }
  }, [challenge, storage]);
  const update = useCallback((next: (c: Challenge | null) => Challenge | null) => setChallenge(next), []);
  return { challenge, update };
}

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

function Pill({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cx("min-h-10 rounded-full border px-3 text-sm pointer-coarse:min-h-11", pressed ? "border-gold/60 bg-gold/10 text-gold" : "border-line text-mist hover:text-parchment")}
    >
      {children}
    </button>
  );
}

const OUTCOME_WORDS = { win: "you win", tie: "a tie", lose: "they win" } as const;

/**
 * The pool loaded from the Pools tab and what it is thrown against: the other
 * side's pool, or a difficulty, and what the book says of it before a throw (pp.
 * 271–275). Shown over the Throws tab's throw.
 */
export function ChallengeSetup({ c, update }: { c: Challenge; update: Challenging["update"] }) {
  const change = (patch: Partial<Challenge>) => update((now) => (now ? { ...now, ...patch } : now));
  const started = c.tests.length > 0 || !!c.relented;
  const notes = [
    c.kind === "opposed" && overbids(c, "me") && "Overbid: your pool is at least double theirs, so you get a free retest (p. 275).",
    c.kind === "opposed" && overbids(c, "them") && "They can overbid: their pool is at least double yours, so they get a free retest (p. 275).",
    automatic(c) && "Your pool is at least double the difficulty: the Storyteller may let you succeed without a test (p. 273).",
    tieNote(c),
    c.theirs !== null &&
      (canBeExceptional(c)
        ? "Win every test outright for an exceptional success."
        : c.kind === "opposed" && c.role === "defender"
          ? "Only the one acting can score an exceptional success."
          : "No exceptional success: your pool isn't greater."),
  ].filter((n): n is string => !!n);
  return (
    <section aria-label="Challenge" className="w-full rounded-lg border border-gold/60 bg-gold/10 p-3 text-sm">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base text-gold">Throwing {c.pool.name}</h2>
          {c.pool.breakdown && <p className="text-xs text-mist">{c.pool.breakdown}</p>}
        </div>
        <button type="button" className="shrink-0 text-xs text-mist underline hover:text-parchment" onClick={() => update(() => null)}>
          Clear
        </button>
      </header>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-mist">Your pool</span>
        <Button variant="secondary" className="min-h-10 px-3" aria-label="Your pool one less" disabled={started || c.mine <= 0} onClick={() => change({ mine: c.mine - 1 })}>
          −
        </Button>
        <strong className="min-w-8 text-center font-display text-2xl text-parchment" aria-label={`Your pool: ${c.mine}`}>
          {c.mine}
        </strong>
        <Button variant="secondary" className="min-h-10 px-3" aria-label="Your pool one more" disabled={started} onClick={() => change({ mine: c.mine + 1 })}>
          +
        </Button>
        <span className="text-xs text-mist">for a wild card</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label="Kind of challenge">
        <Pill pressed={c.kind === "opposed"} onClick={() => !started && change({ kind: "opposed", theirs: c.kind === "opposed" ? c.theirs : null })}>
          Against someone
        </Pill>
        <Pill pressed={c.kind === "static"} onClick={() => !started && change({ kind: "static", theirs: c.kind === "static" ? c.theirs : 8 })}>
          Static
        </Pill>
      </div>
      {c.kind === "opposed" ? (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <div className="flex flex-wrap gap-1" role="group" aria-label="Who acts">
            <Pill pressed={c.role === "attacker"} onClick={() => !started && change({ role: "attacker" })}>
              You act
            </Pill>
            <Pill pressed={c.role === "defender"} onClick={() => !started && change({ role: "defender" })}>
              You defend
            </Pill>
          </div>
          <label className="flex items-center gap-2">
            <span className="text-mist">Their pool</span>
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              max={99}
              className="w-20"
              disabled={started}
              value={c.theirs ?? ""}
              onChange={(e) => change({ theirs: e.target.value === "" ? null : Math.max(0, Math.min(99, Number(e.target.value) || 0)) })}
            />
          </label>
        </div>
      ) : (
        <label className="mt-2 flex items-center gap-2">
          <span className="text-mist">Difficulty</span>
          <Select disabled={started} value={c.theirs ?? ""} onChange={(e) => change({ theirs: Number(e.target.value) })} className="w-auto">
            {!DIFFICULTIES.some((d) => d.rating === c.theirs) && c.theirs !== null && <option value={c.theirs}>{c.theirs}</option>}
            {DIFFICULTIES.map((d) => (
              <option key={d.name} value={d.rating}>
                {d.name} {d.rating}
              </option>
            ))}
          </Select>
          <span className="text-xs text-mist">p. 272</span>
        </label>
      )}
      {c.theirs === null && <p className="mt-2 text-xs text-gold">Ask them for their pool, and enter it to throw this challenge.</p>}
      {notes.length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5 text-xs text-parchment/90" aria-label="Before you throw">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** After this player's throw shows: what the other side showed, tapped in, since the phone can't know. */
export function TheirThrow({ c, update, images }: { c: Challenge; update: Challenging["update"]; images: ThrowImages }) {
  if (!c.pending) return null;
  return (
    <section aria-label="What they showed" className="w-full max-w-sm">
      <h2 className="text-center text-sm text-parchment">What did they show?</h2>
      <div className="mt-1 grid grid-cols-3 gap-2">
        {THROWS.map((t) => (
          <Button key={t} variant="secondary" className="min-h-16 flex-col gap-0.5" aria-label={`They showed ${THROW_NAMES[t]}`} onClick={() => update((now) => (now ? record(now, t) : now))}>
            <span aria-hidden="true" className="aspect-square w-8 text-parchment">
              {images.picture(t)}
            </span>
            {THROW_NAMES[t]}
          </Button>
        ))}
      </div>
      <button type="button" className="mt-1 w-full text-center text-xs text-mist underline hover:text-parchment" onClick={() => update((now) => (now ? { ...now, pending: null } : now))}>
        That throw wasn't for this challenge
      </button>
    </section>
  );
}

/**
 * The challenge's tests so far, its result, and the retests the book allows now:
 * a short list to show at the table. Spending Willpower to retest takes it from the
 * tracker, offline as the tracker does; the pools in this challenge stay as they
 * were (p. 274).
 */
export function ChallengeTests({
  c,
  update,
  images,
  willpower,
  spendWillpower,
}: {
  c: Challenge;
  update: Challenging["update"];
  images: ThrowImages;
  /** Willpower now, when the tracker is here to spend it from. */
  willpower?: number;
  spendWillpower?: () => void;
}) {
  const r = result(c);
  const open = retests(c);
  const choose = (by: RetestBy, side: Side) => {
    if (by === "willpower" && side === "me") spendWillpower?.();
    update((now) => (now ? { ...now, next: { by, side } } : now));
  };
  const relent = (side: Side) => update((now) => (now ? { ...now, relented: side } : now));
  const canRelent = c.tests.length === 0 && !c.relented && !c.pending && c.theirs !== null;
  const spentWillpower = c.tests.some((t) => t.retest?.by === "willpower" && t.retest.side === "me");
  return (
    <section aria-label="Tests and retests" className="flex w-full max-w-sm flex-col gap-2">
      {canRelent && (
        <div className="flex flex-wrap justify-center gap-2 text-xs">
          <Button variant="ghost" className="min-h-10" onClick={() => relent("me")}>
            You relent
          </Button>
          {c.kind === "opposed" && (
            <Button variant="ghost" className="min-h-10" onClick={() => relent("them")}>
              They relent
            </Button>
          )}
        </div>
      )}
      {c.tests.length > 0 && (
        <ol className="divide-y divide-ash rounded-lg border border-ash bg-dusk" aria-label="Tests">
          {c.tests.map((t, i) => {
            const o = outcome(t.mine, t.theirs);
            const to = o === "tie" ? prevails(c, t) : null;
            return (
              <li key={i} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                <span aria-hidden="true" className="aspect-square w-7 text-parchment">
                  {images.picture(t.mine)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-parchment">
                    {THROW_NAMES[t.mine]} against {THROW_NAMES[t.theirs]}: {OUTCOME_WORDS[o]}
                    {to && (to === "me" ? ", yours on pools" : ", theirs on pools")}
                  </span>
                  <span className="block text-xs text-mist">{t.retest ? retestName(t.retest) : "First test"}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
      {r && (
        <div role="status" className={cx("rounded-lg border px-3 py-2 text-center", r.won ? "border-gold/60 bg-gold/10" : "border-blood/60 bg-blood/15")}>
          <p className="font-display text-xl text-parchment">
            {c.relented && (c.relented === "me" ? "You relented. " : "They relented. ")}
            {resultText(c, r)}
          </p>
          {r.critical && <p className="text-sm text-blood-bright">Critical failure: you lost the test without the skill (pp. 273, 275).</p>}
          {!r.final && <p className="text-xs text-mist">So far: a retest can still change it.</p>}
          {r.final && !c.relented && <p className="text-xs text-mist">This stands, unless someone has a merit that retests.</p>}
          {spentWillpower && <p className="text-xs text-mist">Spending Willpower doesn't change the pools in this challenge (p. 274).</p>}
        </div>
      )}
      {open.length > 0 && (
        <div className="flex flex-col gap-1.5" role="group" aria-label="Retests">
          {open.map((o) => {
            const mine = o.side === "me";
            // Spent from the tracker here, or on the Tracker tab when the sheet isn't here yet.
            const spends = o.by === "willpower" && mine && !!spendWillpower;
            const label = spends ? "Spend 1 Willpower to retest" : o.by === "willpower" && mine ? "Retest with Willpower (spend it on the Tracker)" : retestName(o);
            return (
              <Button
                key={`${o.by}-${o.side}`}
                variant={mine ? "secondary" : "ghost"}
                className="min-h-12"
                disabled={spends && willpower !== undefined && willpower <= 0}
                onClick={() => choose(o.by, o.side)}
              >
                {label}
                {spends && willpower !== undefined && <span className="text-xs text-mist">({willpower} left)</span>}
              </Button>
            );
          })}
        </div>
      )}
      {c.next && !c.pending && <p className="text-center text-sm text-gold">{retestName(c.next)}: throw again.</p>}
      {(c.tests.length > 0 || c.relented) && (
        <Button variant="ghost" className="min-h-10 self-center text-xs" onClick={() => update((now) => (now ? restart(now) : now))}>
          Throw this pool again
        </Button>
      )}
      {expecting(c) && c.tests.length === 0 && !c.pending && <p className="text-center text-xs text-mist">Throw, show each other, then tap what they showed.</p>}
    </section>
  );
}
