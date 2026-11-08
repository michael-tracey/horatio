/**
 * What a character's ⋯ on the troupe's Characters list offers its staff (#539),
 * kept apart from the screen so it can be tested. Each item is shown only to staff
 * who may do it where it already lives, and only where it applies: nothing new is
 * allowed, only reachable from here.
 */

import { hasCard } from "../jyhad/taps";

/** The items, by what they open. */
export type StaffAction = "xp" | "equipment" | "status" | "titles" | "give" | "sheet" | "badge" | "jyhad";

/** What decides the items, from the character's roster entry. */
export type ActionTarget = {
  kind: string;
  /** Its home is this troupe (an NPC's always is). */
  home: boolean;
  retired: boolean;
  /** An NPC that can be given to a player as it stands. */
  givable: boolean;
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
 * The items, most used first, then the printouts after a line. Award XP is for a
 * PC whose home this is; equipment and status are given by the home troupe, and
 * equipment only to an active character; only storytellers give an NPC to a
 * player, and not from an archived troupe.
 */
export function staffActions(c: ActionTarget, who: Staffing): { doing: StaffAction[]; printing: StaffAction[] } {
  if (!who.running) return { doing: [], printing: [] };
  const home = c.home || c.kind === "npc";
  const doing: StaffAction[] = [];
  if (c.home && c.kind === "pc") doing.push("xp");
  if (home && !c.retired) doing.push("equipment");
  if (home) doing.push("status");
  doing.push("titles");
  if (c.givable && who.storyteller && !who.archived) doing.push("give");
  // Its Jyhad card (#537), for a character that can have one.
  return { doing, printing: hasCard(c) ? ["sheet", "badge", "jyhad"] : ["sheet", "badge"] };
}
