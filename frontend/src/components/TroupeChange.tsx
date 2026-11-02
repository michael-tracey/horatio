import type { TraitChangeOut } from "../api/types";
import { Badge } from "./ui";

/**
 * Beside a book trait the character's troupe bans (horatio.book_traits): marked
 * "Banned in this troupe", the reason on hover. Those who hold it keep it.
 */
export function BannedMark({ change }: { change?: TraitChangeOut | null }) {
  if (!change?.banned) return null;
  return (
    <span className="ml-2" title={change.ban_reason || undefined}>
      <Badge tone="blood">Banned in this troupe</Badge>
    </span>
  );
}
