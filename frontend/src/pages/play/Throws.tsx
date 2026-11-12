import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui";
import { useDates } from "../../dates";
import { ChallengeSetup, ChallengeTests, TheirThrow, type Challenging } from "./Challenge";
import { expecting } from "./challenge";
import { HORATIO_IMAGES, ThrowFace, type ThrowImages } from "./throwImages";
import { COUNT_IN_STEP_MS, countIn, fairThrow, readThrows, remember, THROW_NAMES, type Throw, type Thrown } from "./throws";

/** Where this browser tab keeps its last throws, so switching tabs or reloading keeps them. */
const KEY = "horatio.throws";

const reducedMotion = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function keptStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export type Throwing = {
  /** The throw on show: the latest, once revealed; none before the first or while counting in. */
  shown: Thrown | null;
  /** The count-in's word now ("Rock…"), while counting in. */
  counting: string | null;
  /** The last few throws, newest first, the one on show among them. */
  past: Thrown[];
  /**
   * Throw now. The Throw button calls it, and a flip of the phone (#669) can too.
   * Does nothing while a throw is counting in.
   */
  throwNow: () => void;
};

/**
 * Rock, paper, scissors on this device: a fair pick, a count-in of about a second
 * (none with reduced motion), then the reveal, with the last few throws kept for
 * this browser tab. Nothing goes to the server, so it works with no signal.
 */
export function useThrows({
  pick = fairThrow,
  storage = keptStorage(),
  onThrown,
}: {
  pick?: () => Throw;
  storage?: Storage | null;
  /** Told of each throw as it is revealed: a challenge from the Pools tab takes it as its test (#698). */
  onThrown?: (thrown: Thrown) => void;
} = {}): Throwing {
  const [past, setPast] = useState<Thrown[]>(() => {
    try {
      return readThrows(storage?.getItem(KEY) ?? null);
    } catch {
      return [];
    }
  });
  const [shown, setShown] = useState<Thrown | null>(past[0] ?? null);
  const [counting, setCounting] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const told = useRef(onThrown);
  told.current = onThrown;

  useEffect(() => {
    try {
      storage?.setItem(KEY, JSON.stringify(past));
    } catch {
      // Kept for this visit only.
    }
  }, [past, storage]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const throwNow = useCallback(() => {
    if (timers.current.length) return;
    // Picked now, at the press, not when it is shown.
    const thrown: Thrown = { throw: pick(), at: new Date().toISOString() };
    const reveal = () => {
      timers.current = [];
      setCounting(null);
      setShown(thrown);
      setPast((p) => remember(p, thrown));
      told.current?.(thrown);
    };
    const steps = countIn(reducedMotion());
    if (!steps.length) return reveal();
    setShown(null);
    setCounting(steps[0]!);
    timers.current = steps.slice(1).map((step, i) => window.setTimeout(() => setCounting(step), (i + 1) * COUNT_IN_STEP_MS));
    timers.current.push(window.setTimeout(reveal, steps.length * COUNT_IN_STEP_MS));
  }, [pick]);

  return { shown, counting, past, throwNow };
}

/**
 * The Play View's Throws tab (#668): a big Throw button for rock, paper or
 * scissors, the throw shown large enough to hold out across a table, and the last
 * three with their times. Tests are settled at the table: each player throws on
 * their own phone and they show each other their screens. A pool thrown from the
 * Pools tab (#698) comes with what the book says each throw means for it.
 */
export function ThrowsTab({
  images = HORATIO_IMAGES,
  challenging,
  willpower,
  spendWillpower,
}: {
  images?: ThrowImages;
  /** The challenge a pool from the Pools tab started, if any. */
  challenging?: Challenging;
  /** Willpower now, and spending one for a retest, when the sheet is here. */
  willpower?: number;
  spendWillpower?: () => void;
}) {
  const c = challenging?.challenge ?? null;
  const update = challenging?.update;
  const { shown, counting, past, throwNow } = useThrows({
    // A throw while the challenge waits for one is its test; any other is a throw like before.
    onThrown: (thrown) => update?.((now) => (now && expecting(now) ? { ...now, pending: thrown.throw } : now)),
  });
  const dates = useDates();
  return (
    <section aria-label="Throws" className="flex flex-col items-center gap-4">
      {c && update && <ChallengeSetup c={c} update={update} />}
      <div aria-live="polite" className="flex min-h-[min(92vw,24rem)] w-full flex-col items-center justify-center rounded-lg border border-ash bg-dusk p-4 text-center">
        {counting ? (
          <p key={counting} className="throw-beat font-display text-5xl text-gold sm:text-6xl">
            {counting}
          </p>
        ) : shown ? (
          <div key={shown.at} className="throw-reveal">
            <ThrowFace images={images} which={shown.throw} />
          </div>
        ) : (
          <p className="max-w-xs text-mist">Throw for rock, paper or scissors, then show the other player your screen.</p>
        )}
      </div>
      <Button className="min-h-16 w-full max-w-sm font-display text-2xl! tracking-wide" onClick={throwNow} disabled={!!counting}>
        Throw
      </Button>
      {c && update && <TheirThrow c={c} update={update} images={images} />}
      {c && update && <ChallengeTests c={c} update={update} images={images} willpower={willpower} spendWillpower={spendWillpower} />}
      {past.length > 0 && (
        <section aria-labelledby="throws-past" className="w-full max-w-sm">
          <h2 id="throws-past" className="text-sm text-mist">
            Last throws
          </h2>
          <ol className="mt-1 divide-y divide-ash rounded-lg border border-ash bg-dusk">
            {past.map((t, i) => (
              <li key={`${i}-${t.at}`} className="flex items-center gap-3 px-3 py-1.5">
                <span aria-hidden="true" className="aspect-square w-10 text-parchment">
                  {images.picture(t.throw)}
                </span>
                <span className="text-parchment">{THROW_NAMES[t.throw]}</span>
                <time dateTime={t.at} className="ml-auto text-sm text-mist tabular-nums">
                  {dates.time(t.at)}
                </time>
              </li>
            ))}
          </ol>
        </section>
      )}
      <p className="max-w-sm text-center text-xs text-mist">Thrown on this phone and sent nowhere, so it works with no signal. Tests: MET: VTM p. 271.</p>
    </section>
  );
}
