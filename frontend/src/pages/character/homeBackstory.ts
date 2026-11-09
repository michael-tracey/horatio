import type { BackstoryStandingOut } from "../../api/types";

/**
 * What asking a troupe to be the character's home says of its backstory (issue #563).
 * A troupe that needs the backstory approved can only approve one that is written,
 * so its player is sent to write it before the request goes rather than after.
 *
 * - "write": not written, and the person asking can write it: the send button goes
 *   to the Backstory tab instead;
 * - "missing": not written, but the person asking can't write it: they're told, and
 *   the request goes as before;
 * - "goes": written: it goes with the request for the troupe to read and approve;
 * - null: the troupe doesn't need one, or the character isn't a player character.
 */
export type HomeBackstory = { need: "write" | "missing" | "goes"; words: string } | null;

export function homeBackstory(
  character: { name: string; kind: string },
  troupe: { name: string; backstory_required: boolean } | undefined,
  standing: Pick<BackstoryStandingOut, "write" | "written"> | undefined,
): HomeBackstory {
  if (!troupe?.backstory_required || character.kind !== "pc" || !standing) return null;
  if (standing.written)
    return { need: "goes", words: `${character.name}'s backstory goes with the request, for ${troupe.name}'s storytellers to read and approve.` };
  return { need: standing.write ? "write" : "missing", words: `${troupe.name} needs a backstory to accept ${character.name}.` };
}
