/**
 * Feeding at a game (MET: VtM core, "Feeding During Game Sessions" and p. 102):
 * 15 minutes out of game for 2 Blood, or with Herd, 5 minutes for Blood equal to
 * its rating (a choice, not a replacement: pp. 102-103). The timer is kept on the device by when it ends, so it stays right
 * through a locked phone, another tab or a reload, and the tap that adds the
 * Blood has its id chosen at the start, so it is never made twice.
 */

/** `herd` is the rating when it is the Herd feed, and 0 for the hunt (so plans saved before the choice read the same). */
export type Plan = { minutes: number; blood: number; herd: number };

/** A feeding under way on this device, or ended and waiting to be seen. */
export type Feeding = {
  /** The id of the Blood tap it makes when it ends. */
  tapId: string;
  /** When it ends, in milliseconds since 1970. */
  endsAt: number;
  plan: Plan;
  /** A notification has gone out for it, the page being hidden when it ended. */
  notified?: boolean;
  /** Once the Blood is added: the Blood before and after, for the result. */
  result?: { before: number; after: number; most: number };
};

/** The standard feed, core p. 294: 15 minutes for 2 Blood. A plan with no Herd in it is a hunt. */
export const hunt: Plan = { minutes: 15, blood: 2, herd: 0 };

/** The Herd feed, core pp. 102-103: 5 minutes for Blood equal to the Herd rating. */
export const herdFeed = (herd: number): Plan => ({ minutes: 5, blood: herd, herd });

/** The feeds on offer: the hunt for anyone, and the Herd feed too with Herd. */
export function feedChoices(herd: number): Plan[] {
  return herd > 0 ? [herdFeed(herd), hunt] : [hunt];
}

/** Which is chosen to start with: Herd when it gives at least as much Blood as hunting (Herd 2 and up). */
export function defaultPlan(herd: number): Plan {
  return herd >= hunt.blood ? herdFeed(herd) : hunt;
}

/** The one line under the choices, comparing the two. */
export function compareText(herd: number): string {
  if (herd <= 0) return "";
  if (herd < hunt.blood) return "Your Herd is quicker, but hunting gives more Blood";
  if (herd === hunt.blood) return "Both give 2 Blood; your Herd takes a third of the time";
  return "Your Herd is quicker and gives more";
}

const herdText = (plan: Plan) => (plan.herd ? ` (Herd ${plan.herd})` : " (hunted)");

/** "5 minutes, +3 Blood (Herd 3)", or "15 minutes, +2 Blood". */
export function planText(plan: Plan): string {
  return `${plan.minutes} minutes, +${plan.blood} Blood${plan.herd ? ` (Herd ${plan.herd})` : ""}`;
}

/** What a choice gives from where Blood is now, capped at the most: "+2 Blood: Blood 7 → 9". */
export function giveText(plan: Plan, value: number, most: number): string {
  const after = fedBlood(plan, value, most);
  if (value >= most) return `Blood is full already, at ${most}`;
  if (value + plan.blood > most) return `+${plan.blood} Blood, but you'll be full at ${most}: Blood ${value} → ${after}`;
  return `+${plan.blood} Blood: Blood ${value} → ${after}`;
}

/** The note on the Blood tap, in the game's log. */
export function feedNote(plan: Plan): string {
  return plan.herd ? `Fed (Herd ${plan.herd})` : "Fed (hunted)";
}

/** What the timer says it is: "Hunting" or "Feeding from your Herd". */
export const feedName = (plan: Plan) => (plan.herd ? "Feeding from your Herd" : "Hunting");

/** Time left as the timer shows it: "04:59", rounding up, never below "00:00". */
export function clockText(ms: number): string {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

/** The Blood after feeding, capped at the most. */
export function fedBlood(plan: Plan, before: number, most: number): number {
  return Math.max(before, Math.min(before + plan.blood, most));
}

/** What the result says: "+3 Blood (Herd 3): Blood 7 → 10.", or "+1 Blood, now full: Blood 11 → 12." */
export function resultText(plan: Plan, result: NonNullable<Feeding["result"]>): { gained: string; rest: string } {
  const { before, after, most } = result;
  if (before >= most) return { gained: "+0 Blood", rest: `${herdText(plan)}: Blood was full already, at ${most}.` };
  const full = before + plan.blood > most ? ", now full" : "";
  return { gained: `+${after - before} Blood`, rest: `${herdText(plan)}${full}: Blood ${before} → ${after}.` };
}

// --- Kept on the device --------------------------------------------------------

const key = (characterId: string) => `horatio.feed.${characterId}`;
const SOUND = "horatio.feed.sound";

function isFeeding(value: unknown): value is Feeding {
  const f = value as Feeding | null;
  return !!f && typeof f.tapId === "string" && typeof f.endsAt === "number" && !!f.plan && typeof f.plan.blood === "number";
}

export function loadFeeding(characterId: string, storage: Storage | undefined = globalThis.localStorage): Feeding | null {
  try {
    const raw = storage?.getItem(key(characterId));
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return isFeeding(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveFeeding(characterId: string, feeding: Feeding | null, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (feeding) storage?.setItem(key(characterId), JSON.stringify(feeding));
    else storage?.removeItem(key(characterId));
  } catch {
    // Private windows and full storage keep nothing; the timer lasts while the page is open.
  }
}

/** Whether the finish plays a sound: on unless turned off on this device. */
export function loadSound(storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    return storage?.getItem(SOUND) !== "off";
  } catch {
    return true;
  }
}

export function saveSound(on: boolean, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    storage?.setItem(SOUND, on ? "on" : "off");
  } catch {
    // Kept for this visit only.
  }
}
