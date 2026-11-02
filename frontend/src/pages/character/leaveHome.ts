import type { WithdrawnOut } from "../../api/types";

/** A request that leaving withdraws, with the XP that comes back: "Celerity 1 → 2 (3 XP back)".
 * A free change undone takes back the XP it refunded. */
export function withdrawnText(request: WithdrawnOut): string {
  if (request.refund > 0) return `${request.what} (${request.refund} XP back)`;
  if (request.refund < 0) return `${request.what} (the ${-request.refund} XP it refunded is taken back)`;
  return request.what;
}
