import type { PlayLogEntry, PlayView, TapIn } from "../../api/types";

/**
 * The Play View's taps on the device. The server works the trackers out from
 * every tap in the order they happened (horatio/play.py); taps not yet sent
 * (the phone is offline, or the request is on its way) are shown on top of the
 * server's view by the same rules, so the screen answers a tap at once.
 */

export type Damage = "normal" | "aggravated";

/** A tap as the device records it: everything the server needs, with its own id. */
export type Tap = TapIn;

/** A log entry, either the server's or a tap still waiting to be sent. */
export type ShownEntry = PlayLogEntry & { pending?: boolean };

export type Shown = Omit<PlayView, "log"> & { log: ShownEntry[] };

const FIXED = ["blood", "willpower", "morality", "beast"] as const;
type Fixed = (typeof FIXED)[number];

function isFixed(tracker: string): tracker is Fixed {
  return (FIXED as readonly string[]).includes(tracker);
}

/** A random id for a tap, even where `crypto.randomUUID` is missing (plain http). */
export function tapId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** A new tap, stamped with when it happened here and the game it was made in. */
export function makeTap(
  what: { kind: Tap["kind"]; tracker?: string; amount?: number; damage?: Damage | null; note?: string; undoes?: string | null },
  gameId: string | null | undefined,
  now: Date = new Date(),
): Tap {
  return {
    id: tapId(),
    happened_at: now.toISOString(),
    game_id: gameId ?? null,
    kind: what.kind,
    tracker: what.tracker ?? "",
    amount: what.amount ?? 0,
    damage: what.damage ?? null,
    note: what.note?.trim() ?? "",
    undoes: what.undoes ?? null,
  };
}

/** What a tracker is called, as the log names it. */
export function trackerName(view: PlayView, tracker: string): string {
  const names: Record<string, string> = {
    blood: "Blood",
    willpower: "Willpower",
    health: "Health",
    morality: view.morality?.name ?? "Morality",
    beast: "Beast traits",
  };
  if (names[tracker]) return names[tracker];
  const found = view.expendables.find((e) => e.key === tracker);
  return found ? (found.detail ? `${found.name}: ${found.detail}` : found.name) : tracker;
}

/** The highest a tracker goes on this sheet; undefined for one it lacks. */
function most(view: PlayView, tracker: string): number | undefined {
  switch (tracker) {
    case "blood":
      return view.blood.most;
    case "willpower":
      return view.willpower.most;
    case "morality":
      return view.morality?.rating;
    case "beast":
      return view.beast.most;
    case "health":
      return view.health.levels.reduce((sum, l) => sum + l.boxes, 0);
  }
  return view.expendables.find((e) => e.key === tracker)?.uses;
}

const clamp = (value: number, top: number) => Math.max(0, Math.min(value, top));

/**
 * Apply one change to `view` (changed in place), as the server does, and say
 * what the tracker was before and after (for health, boxes marked).
 */
export function applyChange(view: PlayView, tracker: string, amount: number, damage: Damage | null = null): [number, number] | null {
  const top = most(view, tracker);
  if (top === undefined) return null;
  if (tracker === "health") {
    const marks = view.health.marks;
    const before = marks.length;
    const kind = damage ?? "normal";
    if (amount > 0) {
      for (let i = 0; i < amount && marks.length < top; i++) marks.push(kind);
    } else {
      for (let i = 0; i < -amount; i++) {
        const at = marks.lastIndexOf(kind);
        if (at < 0) break;
        marks.splice(at, 1);
      }
    }
    return [before, marks.length];
  }
  if (isFixed(tracker)) {
    const t = tracker === "morality" ? view.morality! : view[tracker];
    const before = t.value;
    t.value = clamp(before + amount, top);
    return [before, t.value];
  }
  const found = view.expendables.find((e) => e.key === tracker)!;
  const before = found.left;
  found.left = clamp(before + amount, top);
  return [before, found.left];
}

/** The change as the log reads it: "Blood 7 → 6". */
export function describe(view: PlayView, tap: Pick<Tap, "kind" | "tracker" | "amount" | "damage">, change: [number, number] | null): string {
  if (tap.kind === "note") return "Note";
  if (tap.tracker === "health") {
    const text = `Health: ${tap.amount > 0 ? "took" : "healed"} ${Math.abs(tap.amount)} ${tap.damage ?? "normal"}`;
    return change ? `${text} (${change[0]} → ${change[1]} marked)` : text;
  }
  const name = trackerName(view, tap.tracker);
  return change ? `${name} ${change[0]} → ${change[1]}` : `${name} ${tap.amount > 0 ? "+" : "−"}${Math.abs(tap.amount)}`;
}

function copy(view: PlayView): Shown {
  return {
    ...view,
    blood: { ...view.blood },
    willpower: { ...view.willpower },
    beast: { ...view.beast },
    morality: view.morality ? { ...view.morality } : null,
    health: { ...view.health, marks: [...view.health.marks] },
    expendables: view.expendables.map((e) => ({ ...e })),
    log: view.log.map((e) => ({ ...e })),
  };
}

/**
 * The server's view with the taps still waiting on top, in the order they were
 * made: what the screen shows. Undoing a waiting tap skips it; undoing one the
 * server has takes back what it changed.
 */
export function withPending(view: PlayView, pending: Tap[]): Shown {
  const shown = copy(view);
  const undone = new Set(pending.filter((t) => t.kind === "undo").map((t) => t.undoes));
  const entries: ShownEntry[] = [];
  for (const tap of pending) {
    let change: [number, number] | null = null;
    let text: string;
    if (tap.kind === "undo") {
      const target = pending.find((t) => t.id === tap.undoes);
      const saved = shown.log.find((e) => e.id === tap.undoes);
      if (saved && !saved.undone) {
        saved.undone = true;
        if (saved.kind === "change" && saved.before !== null && saved.after !== null) {
          const delta = saved.after - saved.before;
          applyChange(shown, saved.tracker, -delta, (saved.damage as Damage | null) ?? null);
        }
      }
      const was = target ? entries.find((e) => e.id === target.id)?.text : saved?.text;
      text = was ? `Undid: ${was}` : "Undid a tap";
    } else {
      if (tap.kind === "change" && !undone.has(tap.id)) change = applyChange(shown, tap.tracker, tap.amount, (tap.damage as Damage | null) ?? null);
      else if (tap.kind === "change") change = applyChange(copy(shown), tap.tracker, tap.amount, (tap.damage as Damage | null) ?? null);
      text = describe(shown, tap, change);
    }
    entries.push({
      id: tap.id,
      kind: tap.kind,
      tracker: tap.tracker,
      amount: tap.amount,
      damage: tap.damage ?? null,
      before: change?.[0] ?? null,
      after: change?.[1] ?? null,
      text,
      note: tap.note,
      happened_at: tap.happened_at,
      actor_name: "You",
      by_staff: false,
      undone: undone.has(tap.id),
      undoes: tap.undoes ?? null,
      pending: true,
    });
  }
  // Newest first, as the server sends its log; a waiting tap is newer than any sent.
  shown.log = [...entries.reverse(), ...shown.log].sort((a, b) => Date.parse(b.happened_at) - Date.parse(a.happened_at));
  return shown;
}

/** The tap Undo takes back: the newest not already undone, and not itself an undo. */
export function latestUndoable(log: ShownEntry[]): ShownEntry | undefined {
  return log.find((e) => e.kind !== "undo" && !e.undone);
}

/** Damage marked into the Incapacitated boxes: the character loses their simple action. */
export function incapacitated(view: PlayView): boolean {
  const before = view.health.levels.filter((l) => l.name !== "Incapacitated").reduce((sum, l) => sum + l.boxes, 0);
  return view.health.marks.length > before;
}

// --- The queue of taps not yet sent, kept on the device ------------------------

const key = (characterId: string) => `horatio.play.${characterId}`;

/** Taps waiting to be sent for a character; empty if the browser keeps nothing. */
export function loadQueue(characterId: string, storage: Storage | undefined = globalThis.localStorage): Tap[] {
  try {
    const raw = storage?.getItem(key(characterId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Tap[]).filter((t) => t && typeof t.id === "string") : [];
  } catch {
    return [];
  }
}

export function saveQueue(characterId: string, taps: Tap[], storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (taps.length) storage?.setItem(key(characterId), JSON.stringify(taps));
    else storage?.removeItem(key(characterId));
  } catch {
    // Private windows and full storage keep nothing; the taps stay in memory.
  }
}

/** The queue once a batch has been sent: what was sent is gone, newer taps stay. */
export function afterSending(queue: Tap[], sent: Tap[]): Tap[] {
  const ids = new Set(sent.map((t) => t.id));
  return queue.filter((t) => !ids.has(t.id));
}
