import type { WeaknessOut } from "../api/types";
import { pageText } from "../pages/troupe/bookPage";
import { useClanName } from "./ClanNames";

/** A clan's weakness as the rules send it: the one its troupe plays, or with no troupe, where it varies by troupe, each it may be. */
export type Weakened = { weakness?: string | null; weakness_page?: string | null; weaknesses?: WeaknessOut[] | null };

/** Whether there is a weakness to show. */
export const hasWeakness = (trait: Weakened | undefined | null) => !!(trait?.weakness || trait?.weaknesses?.length);

/**
 * A clan's weakness, with the book's page: the one the troupe plays (#1127). Where the
 * weakness varies by troupe (the Tremere's, which Volume 2 replaced, and the Brujah's,
 * which Volume 2 reads otherwise: each troupe chooses, #1197) and there is no troupe, it
 * says so and gives each, with its page, the default first.
 * Spans throughout, so it sits in a popover as well as a paragraph. `page` is how a page
 * is shown: "(p. 45)" in gold, or " p. 45" as the rules page has it.
 */
export function ClanWeakness({
  trait,
  className = "",
  labelClassName,
  page = "gold",
}: {
  trait: Weakened | undefined | null;
  className?: string;
  labelClassName?: string;
  page?: "gold" | "plain";
}) {
  const named = useClanName();
  if (!trait || !hasWeakness(trait)) return null;
  const pageOf = (p: string | null | undefined) =>
    !p ? null : page === "plain" ? ` ${pageText(p)}` : <span className="text-gold"> ({pageText(p)})</span>;
  const label = <span className={labelClassName}>Weakness:</span>;
  if (trait.weakness) {
    return (
      <span className={`block ${className}`}>
        {label} {named(trait.weakness)}
        {pageOf(trait.weakness_page)}
      </span>
    );
  }
  return (
    <span className={`block ${className}`}>
      {label} varies by troupe. Each troupe plays one of these:
      <span role="list" className="block">
        {trait.weaknesses!.map((w) => (
          <span key={w.book} role="listitem" className="block pl-3">
            {w.label}: {named(w.weakness)}
            {pageOf(w.page)}
          </span>
        ))}
      </span>
    </span>
  );
}
