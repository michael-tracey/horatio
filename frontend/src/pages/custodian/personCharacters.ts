/**
 * Where each of a player's characters stands, for the accordion on their row of
 * Custodian › People (#890).
 */
import type { PlayerCharacter } from "../../api/types";
import type { Note } from "../characterList";

/** Why a retired character left, in the words the Who's Who shows (horatio.leaving). */
const LEFT: Record<string, string> = {
  final_death: "Final Death",
  off_field: "Off-field",
  inactive: "Inactive",
};

/**
 * Active or retired, and why it left; still in creation or waiting for a troupe to
 * accept it; and what it is where it isn't a plain vampire PC: an NPC, a ghoul.
 */
export function characterNotes(c: PlayerCharacter): Note[] {
  const notes: Note[] = [];
  if (c.status === "retired") {
    const why = c.left_reason ? LEFT[c.left_reason] : undefined;
    notes.push({ label: why ? `Retired: ${why}` : "Retired", tone: "mist" });
  } else {
    notes.push({ label: "Active", tone: "mist" });
    if (!c.creation_complete) notes.push({ label: "In creation", tone: "gold" });
    if (c.asking_troupe) notes.push({ label: `Waiting for ${c.asking_troupe}`, tone: "gold" });
  }
  if (c.kind === "npc")
    notes.push({
      label: c.npc_kind_name ? `NPC: ${c.npc_kind_name}` : "NPC",
      tone: "mist",
    });
  else if (c.splat !== "vampire")
    notes.push({
      label: c.splat.charAt(0).toUpperCase() + c.splat.slice(1),
      tone: "mist",
    });
  return notes;
}

/** Its troupe: an NPC's own, or a PC's home troupe, if it has one. */
export function characterTroupe(c: PlayerCharacter): string {
  if (c.kind === "npc") return c.owner_troupe ? `NPC of ${c.owner_troupe}` : "NPC";
  return c.home_troupe ?? "no home troupe";
}

/** Where it opens: its sheet, or a Stock NPC's builder, which stands in for one. */
export function characterLink(c: PlayerCharacter): string {
  return c.kind === "npc" && c.npc_form === "stock" && c.owner_troupe_id ? `/troupes/${c.owner_troupe_id}/npcs/${c.id}` : `/characters/${c.id}`;
}
