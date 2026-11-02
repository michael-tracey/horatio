import type { TraitChangeOut } from "../api/types";
import { wordingLabel, wordingOf, type Wording } from "../houseWording";
import { Markdown } from "./Markdown";
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

/**
 * Beside a merit or flaw the character's troupe moved to another category
 * (horatio.book_traits): "Category changed in this troupe", the book's on hover.
 */
export function CategoryMark({ change }: { change?: Pick<TraitChangeOut, "kind" | "book_kind"> | null }) {
  if (!change?.kind) return null;
  return (
    <span className="ml-2" title={`${change.kind} in this troupe; ${change.book_kind ?? "another"} in the book`}>
      <Badge tone="gold">Category changed in this troupe</Badge>
    </span>
  );
}

/**
 * The troupe's own wording for a book trait, in Markdown with the safe renderer,
 * always marked as the troupe's: under the book's summary, or in its place.
 */
export function HouseWording({ change, className = "" }: { change?: Partial<Wording> | null; className?: string }) {
  const wording = wordingOf(change);
  if (!wording) return null;
  return (
    <div className={`border-l-2 border-gold/60 pl-2 text-parchment ${className}`} data-testid="house-wording">
      <p className="text-xs text-gold">{wordingLabel(wording)}</p>
      <Markdown text={wording.wording} />
    </div>
  );
}
