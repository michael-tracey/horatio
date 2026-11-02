import type { QueuedApproval } from "../../api/types";
import { timeAgo } from "../../components/NotificationBell";

/** Who is asking, for an approval card: "Brujah neonate · tour-joiner · asked 2 days ago". */
export function askedLine(a: Pick<QueuedApproval, "clan" | "age" | "player_name" | "asked_at">, now = Date.now()): string {
  const age = a.age && a.clan ? a.age.toLowerCase() : a.age;
  return [[a.clan, age].filter(Boolean).join(" "), a.player_name ?? "NPC", a.asked_at ? `asked ${timeAgo(a.asked_at, now)}` : ""]
    .filter(Boolean)
    .join(" · ");
}

type Teaching = NonNullable<NonNullable<QueuedApproval["discipline"]>["teaching"]>;

/** Where a purchase a teacher rule asked a teacher for stands, for its card:
 * "Rook's player has not yet confirmed spending 1 Willpower (back after 2 games)." */
export function teachingText(t: Teaching): string {
  const back = `${t.willpower} Willpower (back after ${t.games} ${t.games === 1 ? "game" : "games"})`;
  const who = t.in_troupe ? t.teacher : `${t.teacher}, an NPC named by the player`;
  const actions = t.actions ? ` Learning takes ${t.actions} downtime ${t.actions === 1 ? "action" : "actions"}, owed when approved.` : "";
  switch (t.status) {
    case "asked":
      return `Taught by ${who}. Their player has not yet confirmed spending ${back}; it can be approved once they have.${actions}`;
    case "spent":
      return `Taught by ${who}, who spent ${back}.${actions}`;
    case "refused":
      return `${t.teacher}'s player said no to teaching it: decline it, or the player can withdraw it.`;
    case "given_back":
      return `Taught by ${who}; the Willpower was given back.`;
    default:
      return `Taught by ${who}.${actions}`;
  }
}
