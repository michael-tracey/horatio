import type { components } from "../../api/schema";

type PlanLine = components["schemas"]["XpPlanLineOut"];

/** How far off a planned line is: "Affordable now", "About 2 games away", "12 XP short". */
export function whenText(l: Pick<PlanLine, "held" | "affordable" | "games" | "total">, balance: number): string {
  if (l.held) return "Held already";
  if (l.affordable) return "Affordable now";
  if (l.games != null && l.games > 0) return `About ${l.games} game${l.games === 1 ? "" : "s"} away`;
  return `${l.total - balance} XP short`;
}
