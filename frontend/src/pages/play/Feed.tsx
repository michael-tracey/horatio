import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui";
import { clockText, fedBlood, feedNote, feedPlan, loadFeeding, loadSound, planText, resultText, saveFeeding, saveSound, type Feeding, type Plan } from "./feeding";
import { tapId, type makeTap, type Shown } from "./tracker";
import { useWakeLock } from "./wakeLock";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;

/** The Feed button, beside Blood's own. */
export function FeedButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="secondary" className="min-h-12 rounded-full px-4" onClick={onClick}>
      Feed
    </Button>
  );
}

/**
 * Feeding at a game, from the Play View: a sheet saying what will happen, then a
 * countdown over the page, and at 00:00 blood filling the screen, a sound and
 * the Blood added as an ordinary tap in the game's log, with Undo. The timer is
 * kept on the device by when it ends. If the page is hidden when it ends, the
 * result waits for the player to come back (with a notification where the
 * browser allows one), and only then is the Blood added: once, whatever happens.
 */
export function Feed({ view, asking, onClose, tap }: { view: Shown; asking: boolean; onClose: () => void; tap: Tap }) {
  const characterId = view.character_id;
  const [feeding, setFeeding] = useState<Feeding | null>(() => loadFeeding(characterId));
  const [sound, setSound] = useState(loadSound);
  const shown = usePageShown();
  const running = !!feeding && !feeding.result;
  const now = useNow(running ? feeding.endsAt : null);
  const over = running && now >= feeding.endsAt;
  // The tap this page has made, so a re-render (or React's second run of an effect) never makes it again.
  const added = useRef<string | null>(null);

  const change = (next: Feeding | null) => {
    saveFeeding(characterId, next);
    setFeeding(next);
  };

  // Time is up and the player can see it: add the Blood, once. Only these
  // three start it; the view and tap are read as they are at that moment.
  useEffect(() => {
    if (!feeding || feeding.result || !over || !shown || added.current === feeding.tapId) return;
    added.current = feeding.tapId;
    const most = view.blood.most;
    const already = view.log.find((e) => e.id === feeding.tapId);
    if (already) {
      // Added before (on this device, before a reload): show what it did.
      change({ ...feeding, result: { before: already.before ?? view.blood.value, after: already.after ?? view.blood.value, most } });
      return;
    }
    const before = view.blood.value;
    tap({ id: feeding.tapId, kind: "change", tracker: "blood", amount: feeding.plan.blood, note: feedNote(feeding.plan) });
    change({ ...feeding, result: { before, after: fedBlood(feeding.plan, before, most), most } });
    if (sound) playFed();
    vibrate();
  }, [feeding, over, shown]);

  // Time is up but the page is hidden: tell the player, once.
  useEffect(() => {
    if (!feeding || feeding.result || !over || shown || feeding.notified) return;
    change({ ...feeding, notified: true });
    void notify(feeding.plan);
  }, [feeding, over, shown]);

  const toggleSound = (on: boolean) => {
    saveSound(on);
    setSound(on);
  };

  if (feeding?.result) {
    return (
      <Finished
        plan={feeding.plan}
        result={feeding.result}
        onDone={() => change(null)}
        onUndo={() => {
          tap({ kind: "undo", undoes: feeding.tapId });
          change(null);
        }}
      />
    );
  }
  if (feeding) {
    return <Countdown feeding={feeding} left={feeding.endsAt - now} sound={sound} onSound={toggleSound} onCancel={() => change(null)} />;
  }
  if (!asking) return null;
  const plan = feedPlan(view.herd);
  return (
    <StartSheet
      plan={plan}
      full={view.blood.value >= view.blood.most}
      onCancel={onClose}
      onStart={() => {
        // Starting is a tap, so the browser lets the page play sound and ask to notify.
        unlockSound();
        askToNotify();
        change({ tapId: tapId(), endsAt: Date.now() + plan.minutes * 60_000, plan });
        onClose();
      }}
    />
  );
}

function StartSheet({ plan, full, onStart, onCancel }: { plan: Plan; full: boolean; onStart: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gold/50 bg-dusk p-4 shadow-2xl" role="dialog" aria-label="Feed">
      <div className="mx-auto flex max-w-3xl flex-col gap-2">
        <p className="text-base">
          <strong className="font-display text-gold">Feed</strong> — {planText(plan)}.
        </p>
        <p className="text-sm text-mist">Tell a storyteller or narrator you're feeding first.</p>
        {full && <p className="text-sm text-mist">Blood is full now, so feeding adds nothing unless some is spent first.</p>}
        <div className="flex gap-2">
          <Button className="min-h-12 flex-1" onClick={onStart}>
            Start
          </Button>
          <Button variant="ghost" className="min-h-12" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

/** The timer over the page: large, with the screen kept awake, and Cancel the whole time. */
function Countdown({
  feeding,
  left,
  sound,
  onSound,
  onCancel,
}: {
  feeding: Feeding;
  left: number;
  sound: boolean;
  onSound: (on: boolean) => void;
  onCancel: () => void;
}) {
  useWakeLock(true);
  return (
    <div className="fixed inset-0 z-30 flex flex-col items-center justify-center gap-6 bg-night px-4 text-center" role="dialog" aria-modal="true" aria-label="Feeding">
      <div>
        <h2 className="text-xl text-gold">Feeding</h2>
        <p className="text-sm text-mist">
          Out of game. +{feeding.plan.blood} Blood{feeding.plan.herd ? ` (Herd ${feeding.plan.herd})` : ""} when the time is up.
        </p>
      </div>
      <p role="timer" aria-label="Time left" className="font-display text-8xl leading-none text-parchment tabular-nums sm:text-9xl">
        {clockText(left)}
      </p>
      <p className="max-w-xs text-xs text-mist">The time is kept on this device, so you can lock the phone or leave the page and come back.</p>
      <div className="flex flex-col items-center gap-3">
        <label className="flex min-h-10 items-center gap-2 text-sm text-mist">
          <input type="checkbox" className="h-5 w-5 accent-[var(--color-gold)]" checked={sound} onChange={(e) => onSound(e.target.checked)} />
          Sound
        </label>
        <Button variant="secondary" className="min-h-12 min-w-40" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** Blood rising from the bottom (or fading in, with reduced motion), and what feeding gave. */
function Finished({ plan, result, onDone, onUndo }: { plan: Plan; result: NonNullable<Feeding["result"]>; onDone: () => void; onUndo: () => void }) {
  const [motion] = useState(() => !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const { gained, rest } = resultText(plan, result);
  return (
    <div className="fixed inset-0 z-30 overflow-hidden bg-night" role="dialog" aria-modal="true" aria-label="You fed">
      <div className={motion ? "feed-rise absolute inset-0" : "feed-fade absolute inset-0"} data-motion={motion ? "fill" : "fade"} data-testid="feed-fill">
        <svg className="absolute inset-x-0 top-0 h-6 w-full -translate-y-full text-blood-bright" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 10 Q 12.5 0 25 6 T 50 6 T 75 6 T 100 4 V10 Z" fill="currentColor" />
        </svg>
        <div className="h-full w-full bg-linear-to-b from-blood-bright via-blood to-[#4a0f1b]" />
      </div>
      <div className={motion ? "feed-after relative flex h-full items-center justify-center px-4" : "relative flex h-full items-center justify-center px-4"}>
        <div className="flex w-full max-w-sm flex-col items-center gap-4 rounded-lg border border-parchment/30 bg-night/85 p-6 text-center shadow-2xl">
          <p className="font-display text-2xl text-parchment">You fed.</p>
          <p>
            <strong className="font-display text-4xl text-blood-bright">{gained}</strong>
            <span className="text-parchment">{rest}</span>
          </p>
          <div className="flex w-full gap-2">
            <Button className="min-h-12 flex-1" onClick={onDone} autoFocus>
              Done
            </Button>
            <Button variant="secondary" className="min-h-12" onClick={onUndo}>
              Undo
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- The browser's part ----------------------------------------------------------

/** Whether the page is showing (not another tab, another app or a locked phone). */
function usePageShown(): boolean {
  const [shown, setShown] = useState(() => document.visibilityState === "visible");
  useEffect(() => {
    const look = () => setShown(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", look);
    return () => document.removeEventListener("visibilitychange", look);
  }, []);
  return shown;
}

/** The time now, a few times a second while there is an end to count to, and at the end itself. */
function useNow(endsAt: number | null): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (endsAt === null) return;
    const tick = () => setNow(Date.now());
    tick();
    const every = window.setInterval(tick, 250);
    const atEnd = window.setTimeout(tick, Math.max(0, endsAt - Date.now()) + 50);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(every);
      window.clearTimeout(atEnd);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [endsAt]);
  return now;
}

let audio: AudioContext | null = null;

function audioContext(): AudioContext | null {
  if (audio) return audio;
  const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Context) return null;
  try {
    audio = new Context();
  } catch {
    return null;
  }
  return audio;
}

/** Browsers start sound only after a tap; Start is one, and the context stays allowed. */
function unlockSound() {
  void audioContext()?.resume().catch(() => {});
}

/** Two heartbeats and a low bell, made here rather than loaded: about two seconds. */
function playFed() {
  const ctx = audioContext();
  if (!ctx) return;
  void ctx.resume().catch(() => {});
  const t = ctx.currentTime + 0.05;
  const out = ctx.createGain();
  out.gain.value = 0.5;
  out.connect(ctx.destination);
  const note = (type: OscillatorType, from: number, to: number, at: number, length: number, peak: number) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(from, at);
    osc.frequency.exponentialRampToValueAtTime(to, at + length);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak, at + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
    osc.connect(gain).connect(out);
    osc.start(at);
    osc.stop(at + length + 0.05);
  };
  // Lub-dub, twice, then the bell: A4 and E5 together.
  for (const beat of [0, 0.7]) {
    note("triangle", 180, 70, t + beat, 0.16, 0.9);
    note("triangle", 160, 60, t + beat + 0.22, 0.14, 0.6);
  }
  note("sine", 440, 438, t + 1.4, 1.4, 0.35);
  note("sine", 659.3, 657, t + 1.4, 1.2, 0.2);
}

function vibrate() {
  try {
    navigator.vibrate?.([120, 80, 120, 300, 120, 80, 120]);
  } catch {
    // Not on this device.
  }
}

function askToNotify() {
  try {
    if (typeof Notification !== "undefined" && Notification.permission === "default") void Promise.resolve(Notification.requestPermission()).catch(() => {});
  } catch {
    // Older browsers ask differently, or not at all.
  }
}

/** A notification that time is up, where the browser allows one. */
async function notify(plan: Plan) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  const title = "Feeding is done";
  const options = { body: `Open the Play View to add your +${plan.blood} Blood.`, tag: "horatio-feed" };
  try {
    // Phones show notifications only through a service worker, where there is one.
    const registration = await navigator.serviceWorker?.getRegistration();
    if (registration) return void (await registration.showNotification(title, options));
  } catch {
    // Fall through to a plain notification.
  }
  try {
    new Notification(title, options);
  } catch {
    // Not allowed here after all.
  }
}
