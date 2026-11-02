import type { SheetOut } from "../../api/types";
import { useDates, type Dates } from "../../dates";

type FreeChanges = NonNullable<SheetOut["free_changes"]>;

/** How much of a new character's free changes is left, in its troupe's terms: "Free changes until Mon 14 Dec", "Free changes: 2 games left". */
export function freeChangesText(free: FreeChanges, dates: Dates, now: Date = new Date()): string {
  if (free.kind === "date" && free.ends_at) return `Free changes until ${dates.dueDay(free.ends_at, now)}`;
  const left = free.games_left ?? 0;
  return `Free changes: ${left === 1 ? "1 game" : `${left} games`} left`;
}

/**
 * A new character's free changes (horatio.free_changes), while they are open: lowering or
 * removing a trait refunds its full XP, as during creation, and the home troupe reviews
 * each change. Its player is told when they end.
 */
export function FreeChangesNotice({ free }: { free: FreeChanges }) {
  return <FreeChangesText free={free} dates={useDates()} />;
}

export function FreeChangesText({ free, dates, now }: { free: FreeChanges; dates: Dates; now?: Date }) {
  return (
    <section aria-label="Free changes" className="rounded-md border border-gold/40 bg-gold/10 px-3 py-2 text-sm">
      <p className="text-gold">{freeChangesText(free, dates, now)}</p>
      <p className="text-mist">
        Until then, lowering or removing a trait gives back its full XP, as in creation, and the home troupe reviews each change
        {free.excluded.length > 0 ? `. ${listed(free.excluded)} ${free.excluded.length === 1 ? "is" : "are"} never refunded so` : ""}.
        {free.kind === "games" ? " A game counts once the character checks in." : ""}
      </p>
    </section>
  );
}

/** "Arcane and Efficient Learner". */
function listed(names: string[]): string {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : (names[0] ?? "");
}
