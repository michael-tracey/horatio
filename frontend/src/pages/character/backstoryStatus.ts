/**
 * Where a backstory stands with the troupe reading it, in plain words, and what
 * the person looking at it can do next (issue #368).
 */
import type { BackstoryStandingOut } from "../../api/types";

export type BackstoryStatus = {
  badge: string;
  /** Blood: the person looking needs to act. Gold: it waits on someone else. Mist: settled. */
  tone: "mist" | "gold" | "blood";
  words: string;
};

type Standing = Pick<BackstoryStandingOut, "write" | "review" | "written" | "troupe_name" | "required" | "state" | "approved" | "changed_since_approval">;

/**
 * The status for whoever is looking: its player is told whether they need to do
 * anything, the storytellers reading it what is theirs to do. `asking` is true while
 * the character asks that troupe to make it home, when a troupe that needs the
 * backstory approved first holds the character back until it is.
 */
export function backstoryStatus(b: Standing, approvedBy: string, asking: boolean): BackstoryStatus | null {
  const t = b.troupe_name;
  const player = b.write;
  const reader = b.review && !player;
  if (!t)
    return player
      ? { badge: "No troupe yet", tone: "mist", words: "No troupe reads it yet: its storytellers will once the character asks a troupe to be its home." }
      : null;
  const holds = asking && b.required;
  if (b.changed_since_approval)
    return player
      ? { badge: "Changed", tone: "gold", words: `Changed since ${t} approved it. Waiting for its storytellers to read the changes: nothing for you to do yet.` }
      : reader
        ? { badge: "Changed", tone: "blood", words: `Changed since ${t} approved it. Read the changes, then approve it again or send it back.` }
        : { badge: "Changed", tone: "gold", words: `Changed since ${t} approved it.` };
  if (b.approved) return { badge: "Approved", tone: "mist", words: `Approved by ${t}${approvedBy}.${player ? " Nothing for you to do." : ""}` };
  if (b.state === "returned")
    return player
      ? { badge: "Changes asked for", tone: "blood", words: `${t}'s storytellers asked for changes: see their feedback below, revise it, then resubmit it.` }
      : { badge: "Sent back", tone: "gold", words: `Sent back to the player with feedback. Waiting for them to revise it.` };
  if (b.state === "resubmitted")
    return player
      ? { badge: "Revised", tone: "gold", words: `Revised and back with ${t}'s storytellers. Nothing for you to do yet.` }
      : reader
        ? { badge: "Revised", tone: "blood", words: "The player revised it. Read it, then approve it or send it back." }
        : { badge: "Revised", tone: "gold", words: `Revised and back with ${t}'s storytellers.` };
  if (!b.written)
    return player
      ? {
          badge: "Not written",
          tone: holds ? "blood" : "gold",
          words: holds
            ? `${t} needs it approved before accepting the character. Write it so its storytellers can read it.`
            : `Nothing written yet. ${t}'s storytellers will read it once you write it.`,
        }
      : { badge: "Not written", tone: "gold", words: "Nothing written yet." };
  if (player)
    return {
      badge: "Waiting",
      tone: "gold",
      words: holds
        ? `Waiting for ${t}'s storytellers to approve it before they accept the character. Nothing for you to do yet.`
        : `Waiting for ${t}'s storytellers to approve it. Nothing for you to do yet.`,
    };
  return reader
    ? { badge: "To read", tone: "blood", words: `Not yet approved. Read it, then approve it or send it back with feedback.` }
    : { badge: "Not yet approved", tone: "gold", words: `Not yet approved by ${t}.` };
}
