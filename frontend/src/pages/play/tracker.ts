import type { InfluenceDetailsIn, PlayLogEntry, PlayView, TapIn, TemporaryDerangementIn } from "../../api/types";
import { TYPE_NAMES } from "../../influence";
import { applySwitch, describeSwitch, healthMost, SWITCH } from "./powers";

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

const FIXED = ["blood", "willpower", "morality", "beast", "derangements"] as const;
/** A ghoul drinking vitae: +n adds that much to its vitae, which is `blood` (MET: VtM core p. 297). */
export const DRANK = "drank";
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
  what: {
    /** Chosen ahead, for a tap that must never be made twice (feeding's Blood). */
    id?: string;
    kind: Tap["kind"];
    tracker?: string;
    amount?: number;
    damage?: Damage | null;
    note?: string;
    undoes?: string | null;
    influence?: InfluenceDetailsIn | null;
    /** Adding a temporary derangement: its name and where it came from. */
    derangement?: TemporaryDerangementIn | null;
  },
  gameId: string | null | undefined,
  now: Date = new Date(),
): Tap {
  return {
    id: what.id ?? tapId(),
    happened_at: now.toISOString(),
    game_id: gameId ?? null,
    kind: what.kind,
    tracker: what.tracker ?? "",
    amount: what.amount ?? 0,
    damage: what.damage ?? null,
    note: what.note?.trim() ?? "",
    undoes: what.undoes ?? null,
    influence: what.influence ?? null,
    derangement: what.derangement ?? null,
  };
}

/** The standing to ask a spend's details with: the tracker is an Influences counter whose spends are logged. */
export function influenceStanding(view: PlayView, tracker: string) {
  const type = view.expendables.find((e) => e.key === tracker)?.influence;
  return type ? view.influence.find((s) => s.type === type) : undefined;
}

/** An influence spend as the game's log reads it, as the server says it: "Elite: 5: No Party Crashers (News Media), To secure the Weather". */
export function spendText(view: PlayView, tracker: string, amount: number, details: InfluenceDetailsIn | null | undefined): string | null {
  const standing = influenceStanding(view, tracker);
  if (!standing || amount >= 0) return null;
  const name = TYPE_NAMES[standing.type] + (amount < -1 ? ` ×${-amount}` : "");
  const action = details && standing.actions.find((a) => a.key === details.action);
  if (!details || !action) return `${name}: details to come`;
  const said = action.label + (details.specialization ? ` (${details.specialization})` : "");
  return details.purpose?.trim() ? `${name}: ${said}, ${details.purpose.trim()}` : `${name}: ${said}`;
}

/** A temporary derangement's tracker in taps: +1 adds it, −1 removes it. */
export const TEMPORARY = "derangement:";

/** A temporary derangement as the log names it: "Phobia: fire, from Voice of Madness". */
export function temporaryLabel(t: { name: string; source: string }): string {
  return t.source ? `${t.name}, from ${t.source}` : t.name;
}

/** Spending an abiding or innate status for the game: "status:Authority". */
export const STATUS = "status:";
/** Spending a fleeting status for good, by its record: "held:<id>". */
export const HELD = "held:";

export function isStatus(tracker: string): boolean {
  return tracker.startsWith(STATUS) || tracker.startsWith(HELD);
}

/** The status a tap spends, as the Status tab lists it. */
export function statusEntry(view: PlayView, tracker: string) {
  return isStatus(tracker) ? view.status?.carried.find((c) => c.key === tracker) : undefined;
}

/** A Retainer's health and Blood: "retainer:Bocephus/health" (core p. 105). */
export const RETAINER = "retainer:";

/** The Retainer's tracker a tap names, or undefined for another tracker. */
export function retainerTracker(view: PlayView, tracker: string) {
  if (!tracker.startsWith(RETAINER)) return undefined;
  const at = tracker.lastIndexOf("/");
  const retainer = (view.retainers ?? []).find((r) => r.key === tracker.slice(0, at));
  if (!retainer) return undefined;
  const what = tracker.slice(at + 1);
  return { retainer, what, track: what === "blood" ? retainer.blood : what === "health" ? retainer.health : null };
}

/** What a tracker is called, as the log names it. */
export function trackerName(view: PlayView, tracker: string): string {
  const names: Record<string, string> = {
    blood: view.blood_name,
    [DRANK]: "Drank vitae",
    willpower: "Willpower",
    health: "Health",
    morality: view.morality?.name ?? "Morality",
    beast: "Beast traits",
    derangements: "Derangement traits",
  };
  if (names[tracker]) return names[tracker];
  const found = view.expendables.find((e) => e.key === tracker);
  if (found) return found.detail ? `${found.name}: ${found.detail}` : found.name;
  const temporary = view.derangements.temporary.find((t) => t.key === tracker);
  if (temporary) return temporaryLabel(temporary);
  const kept = retainerTracker(view, tracker);
  if (kept) return `${kept.retainer.name || "Retainer"}: ${kept.what === "blood" ? "Blood" : "health"}`;
  const status = statusEntry(view, tracker);
  if (status) return status.name;
  if (tracker.startsWith(STATUS)) return tracker.slice(STATUS.length);
  const power = tracker.startsWith(SWITCH) ? view.powers.find((p) => SWITCH + p.key === tracker) : undefined;
  return power?.name ?? tracker;
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
      return view.panels.beast ? view.beast.most : undefined;
    case DRANK:
      return view.vitae ? view.blood.most : undefined;
    case "derangements":
      return view.derangements.most;
    case "health":
      return healthMost(view);
  }
  if (tracker.startsWith(TEMPORARY)) return view.derangements.temporary.some((t) => t.key === tracker) ? 1 : undefined;
  if (tracker.startsWith(RETAINER)) return retainerTracker(view, tracker)?.track?.most;
  if (isStatus(tracker)) return statusEntry(view, tracker) ? 1 : undefined;
  return view.expendables.find((e) => e.key === tracker)?.uses;
}

const clamp = (value: number, top: number, least = 0) => Math.max(least, Math.min(value, top));

/**
 * Apply one change to `view` (changed in place), as the server does, and say
 * what the tracker was before and after (for health, boxes marked). What
 * switching a form or power also did goes in `said`.
 */
export function applyChange(view: PlayView, tracker: string, amount: number, damage: Damage | null = null, said: string[] = []): [number, number] | null {
  if (tracker.startsWith(SWITCH)) return applySwitch(view, tracker.slice(SWITCH.length), amount, said);
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
  // A ghoul's vitae: drunk into a full pool it takes the place of human Blood, which is never spent.
  if (view.vitae && (tracker === "blood" || tracker === DRANK)) {
    const before = view.blood.value;
    view.blood.value = clamp(before + amount, top);
    view.vitae.human = clamp(view.vitae.human, view.vitae.pool - view.blood.value);
    return [before, view.blood.value];
  }
  if (isFixed(tracker)) {
    const t = tracker === "morality" ? view.morality! : view[tracker];
    const before = t.value;
    // A Malkavian never has fewer than 1 Derangement trait.
    t.value = clamp(before + amount, top, tracker === "derangements" ? view.derangements.least : 0);
    return [before, t.value];
  }
  if (tracker.startsWith(TEMPORARY)) {
    const temporary = view.derangements.temporary.find((t) => t.key === tracker)!;
    const before = temporary.held ? 1 : 0;
    temporary.held = clamp(before + amount, top) > 0;
    return [before, temporary.held ? 1 : 0];
  }
  const status = statusEntry(view, tracker);
  if (status) {
    const before = status.spent ? 0 : 1;
    const after = clamp(before + amount, top);
    status.spent = after === 0;
    if (!status.spent) status.spent_by = null;
    return [before, after];
  }
  const kept = retainerTracker(view, tracker)?.track;
  if (kept) {
    const before = kept.value;
    kept.value = clamp(before + amount, top);
    return [before, kept.value];
  }
  const found = view.expendables.find((e) => e.key === tracker)!;
  const before = found.left;
  found.left = clamp(before + amount, top);
  return [before, found.left];
}

/** The change as the log reads it: "Blood 7 → 6". */
export function describe(
  view: PlayView,
  tap: Pick<Tap, "kind" | "tracker" | "amount" | "damage" | "influence">,
  change: [number, number] | null,
  said: string[] = [],
): string {
  if (tap.kind === "note") return "Note";
  if (tap.tracker.startsWith(SWITCH)) return describeSwitch(view, tap.tracker.slice(SWITCH.length), tap.amount, said);
  const spent = tap.kind === "change" ? spendText(view, tap.tracker, tap.amount, tap.influence) : null;
  if (spent) return spent;
  if (tap.tracker === DRANK) {
    const text = `Drank ${tap.amount} vitae`;
    return change ? `${text}: Vitae ${change[0]} → ${change[1]}` : text;
  }
  if (tap.tracker === "health") {
    const text = `Health: ${tap.amount > 0 ? "took" : "healed"} ${Math.abs(tap.amount)} ${tap.damage ?? "normal"}`;
    return change ? `${text} (${change[0]} → ${change[1]} marked)` : text;
  }
  const name = trackerName(view, tap.tracker);
  if (isStatus(tap.tracker)) {
    if (tap.amount > 0) return `${name} back`;
    return tap.tracker.startsWith(HELD) ? `Spent ${name} for good` : `Spent ${name}`;
  }
  if (tap.tracker.startsWith(TEMPORARY)) return `Temporary derangement ${tap.amount > 0 ? "added" : "removed"}: ${name}`;
  return change ? `${name} ${change[0]} → ${change[1]}` : `${name} ${tap.amount > 0 ? "+" : "−"}${Math.abs(tap.amount)}`;
}

function copy(view: PlayView): Shown {
  return {
    ...view,
    blood: { ...view.blood },
    willpower: { ...view.willpower },
    beast: { ...view.beast },
    vitae: view.vitae ? { ...view.vitae } : null,
    derangements: { ...view.derangements, temporary: view.derangements.temporary.map((t) => ({ ...t })) },
    morality: view.morality ? { ...view.morality } : null,
    health: { ...view.health, marks: [...view.health.marks] },
    expendables: view.expendables.map((e) => ({ ...e })),
    retainers: (view.retainers ?? []).map((r) => ({ ...r, health: { ...r.health }, blood: r.blood ? { ...r.blood } : null })),
    powers: view.powers.map((p) => ({ ...p })),
    status: view.status ? { ...view.status, carried: view.status.carried.map((c) => ({ ...c })) } : null,
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
      // A temporary derangement added on this device, not yet on the server.
      if (tap.derangement && !shown.derangements.temporary.some((t) => t.key === tap.tracker)) {
        shown.derangements.temporary.push({ key: tap.tracker, name: tap.derangement.name, source: tap.derangement.source ?? "", held: false });
      }
      const said: string[] = [];
      if (tap.kind === "change" && !undone.has(tap.id)) {
        change = applyChange(shown, tap.tracker, tap.amount, (tap.damage as Damage | null) ?? null, said);
        // The spend Undo on the Status tab takes back.
        const status = statusEntry(shown, tap.tracker);
        if (status?.spent && tap.amount < 0) status.spent_by = tap.id;
      }
      else if (tap.kind === "change") change = applyChange(copy(shown), tap.tracker, tap.amount, (tap.damage as Damage | null) ?? null, said);
      text = describe(shown, tap, change, said);
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
  const before = healthMost({ ...view, health: { ...view.health, levels: view.health.levels.filter((l) => l.name !== "Incapacitated") } });
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
