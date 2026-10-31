import type { QueuedApproval } from "../../api/types";
import { timeAgo } from "../../components/NotificationBell";

/** Who is asking, for an approval card: "Brujah neonate · tour-joiner · asked 2 days ago". */
export function askedLine(a: Pick<QueuedApproval, "clan" | "age" | "player_name" | "asked_at">, now = Date.now()): string {
  const age = a.age && a.clan ? a.age.toLowerCase() : a.age;
  return [[a.clan, age].filter(Boolean).join(" "), a.player_name ?? "NPC", a.asked_at ? `asked ${timeAgo(a.asked_at, now)}` : ""]
    .filter(Boolean)
    .join(" · ");
}
