import type { components } from "../../api/schema";

type PlanLine = components["schemas"]["XpPlanLineOut"];
type Award = components["schemas"]["XpPlanAwardOut"];

/**
 * How far off a planned line is: "Affordable now", "About 2 games away", "12 XP short".
 * `spare` is the XP left once the cart is bought; `downtime`, whether the games
 * away count the troupe's downtime XP too.
 */
export function whenText(l: Pick<PlanLine, "held" | "in_cart" | "affordable" | "games" | "total">, spare: number, downtime = false): string {
  if (l.in_cart) return "In the cart";
  if (l.held) return "Held already";
  if (l.affordable) return "Affordable now";
  if (l.games != null && l.games > 0) return `About ${l.games} game${l.games === 1 ? "" : "s"} away${downtime ? ", counting downtime XP" : ""}`;
  return `${l.total - spare} XP short`;
}

const tenths = (n: number) => Math.round(n * 10) / 10;

/** The XP a game usually brings, and where from: "about 9.5 XP a game: 8 from the troupe's session XP, and 1.5 from downtimes (…)". */
export function awardText(a: Award): string {
  const downtime = a.downtime > 0 ? `from downtimes (${a.downtime_source})` : null;
  if (a.per_game > 0 && downtime) return `about ${tenths(a.per_game + a.downtime)} XP a game: ${a.per_game} from ${a.source}, and ${a.downtime} ${downtime}`;
  if (downtime) return `about ${a.downtime} XP a game, ${downtime}`;
  return `about ${a.per_game} XP a game, from ${a.source}`;
}

/** What the cart does to the XP unspent, after "30 XP unspent": ", 15 of it for the cart". */
export function cartText(cost: number): string {
  if (cost > 0) return `, ${cost} of it for the cart`;
  if (cost < 0) return `, and ${-cost} XP back from the cart`;
  return "";
}
