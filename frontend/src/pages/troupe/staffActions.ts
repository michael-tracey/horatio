/**
 * What a character's ⋯ on the troupe's Characters list offers its staff (#539),
 * PCs and NPCs alike (#556), kept apart from the screen so it can be tested. Each
 * item is shown only to staff who may do it where it already lives, and only where
 * it applies: nothing new is allowed, only reachable from here.
 */

import { hasCard } from "../jyhad/taps";

/** The items, by what they open. */
export type StaffAction = "play" | "xp" | "equipment" | "status" | "titles" | "listing" | "give" | "claim" | "npc" | "sheet" | "badge" | "jyhad";

/** What decides the items, from the character's roster entry. */
export type ActionTarget = {
  kind: string;
  /** Its home is this troupe (an NPC's always is). */
  home: boolean;
  retired: boolean;
  /** An NPC that can be given to a player as it stands. */
  givable: boolean;
  /** An NPC's form: "sheeted", or "stock" for one with no sheet; null for a PC. */
  npc_form: string | null;
  /** For its Jyhad card (#537): a vampire (one with a social age) with a picture. */
  picture: string | null;
  social_age: string;
};

/** Who is looking, in this troupe. An archived troupe is closed to all but the
 * custodian, so only the custodian sees its list. */
export type Staffing = {
  /** Its storytellers, assistant storytellers and the custodian. */
  running: boolean;
  /** Its storytellers and the custodian. */
  storyteller: boolean;
  archived: boolean;
};

/**
 * The items, most used first, then the printouts after a line. An NPC opens with
 * its Play View; Award XP is for a PC whose home this is; equipment and status are
 * given by the home troupe, and equipment only to an active character; an NPC is
 * listed on the Who's Who by hand; only storytellers give an NPC to a player or
 * make a claim link for it, and not from an archived troupe. A retired PC whose home
 * this is can be copied as an NPC (#764), however it left. A Stock NPC has no
 * sheet to print; Badge… shows what the badge says, takes a note and prints it.
 */
export function staffActions(c: ActionTarget, who: Staffing): { doing: StaffAction[]; printing: StaffAction[] } {
  if (!who.running) return { doing: [], printing: [] };
  const npc = c.kind === "npc";
  const home = c.home || npc;
  const doing: StaffAction[] = [];
  if (npc) doing.push("play");
  if (c.home && c.kind === "pc") doing.push("xp");
  if (home && !c.retired) doing.push("equipment");
  if (home) doing.push("status");
  doing.push("titles");
  if (npc) doing.push("listing");
  if (c.givable && who.storyteller && !who.archived) doing.push("give", "claim");
  if (c.kind === "pc" && c.home && c.retired && !who.archived) doing.push("npc");
  const printing: StaffAction[] = c.npc_form === "stock" ? ["badge"] : ["sheet", "badge"];
  // Its Jyhad card (#537), for a character that can have one.
  if (hasCard(c)) printing.push("jyhad");
  return { doing, printing };
}
