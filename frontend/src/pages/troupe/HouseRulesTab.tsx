import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SplatHouseRulesOut, TroupeOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { HouseMark, HouseSummary } from "../../components/HouseMark";
import { Card, ErrorText, Loading } from "../../components/ui";
import { pageText } from "./bookPage";

/** How a check is played, in a player's words. */
export const PLAYED: Record<string, string> = {
  refuse: "Not allowed",
  complete: "Needed to finish character creation",
  review: "Allowed, for the storytellers to review",
  note: "Allowed, noted for the storytellers",
  off: "Does not apply",
};

const BACKSTORY: Record<string, string> = {
  free: "Write your character's backstory freely.",
  either: "Write your character's backstory freely, or answer the troupe's questions.",
  wizard: "Answer the troupe's questions, then edit the backstory they build.",
};

/** The book's starting XP for a new character. */
const BOOK_XP = 30;

/**
 * What the troupe plays differently from the book, for its players to read before
 * they build or buy: its own prices, starting points, checks, merits and flaws,
 * downtime actions and other house rules, and how backstories are written. Read
 * only; its storytellers change them under Customise.
 */
export function HouseRulesTab({ troupe, staff }: { troupe: TroupeOut; staff: boolean }) {
  const rules = useQuery({
    queryKey: ["house-rules", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/house-rules", { params: { path: { troupe_id: troupe.id } } })),
  });
  if (rules.isPending) return <Loading />;
  if (rules.error) return <ErrorText error={rules.error} />;
  const r = rules.data;
  const xp = troupe.xp_floor !== BOOK_XP;
  const bySplat = (pick: (s: SplatHouseRulesOut) => unknown[]) => r.splats.filter((s) => pick(s).length > 0);
  const costs = bySplat((s) => s.costs);
  const starting = bySplat((s) => s.starting);
  const actions = bySplat((s) => s.actions);
  const nothing = !xp && !costs.length && !starting.length && !actions.length && !r.checks.length && !r.house_traits.length && !r.other.length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-mist">
          What {troupe.name} plays differently from the book. They apply to characters whose home troupe this is, and to characters being built for it.
          Everything not listed here is as written.
        </p>
        <span className="flex flex-wrap gap-x-4 gap-y-1">
          <Link to={`/rules?troupe=${troupe.id}`} className="text-sm text-mist underline hover:text-parchment">
            Browse every rule as played here
          </Link>
          {staff && (
            <Link to={`/troupes/${troupe.id}/rules`} className="text-sm text-mist underline hover:text-parchment">
              See them in Customise
            </Link>
          )}
        </span>
      </div>

      {nothing && (
        <Card>
          <EmptyState title={`${troupe.name} plays everything as written.`}>Its storytellers have set no house rules yet.</EmptyState>
        </Card>
      )}

      {costs.length > 0 && (
        <Card title="Costs">
          {costs.map((s) => (
            <SplatPart key={s.splat} label={s.label} split={costs.length > 1 || s.splat !== "vampire"}>
              {s.costs.map((c) => (
                <Row
                  key={`${c.category}/${c.subject}`}
                  subject={
                    <>
                      {c.subject}
                      {c.page && <span className="text-mist"> {pageText(c.page)}</span>}
                    </>
                  }
                  now={c.price_text}
                  book={c.book_text}
                  note={c.text}
                />
              ))}
            </SplatPart>
          ))}
        </Card>
      )}

      {(xp || starting.length > 0) && (
        <Card title="Starting points">
          {xp && (
            <ul className="divide-y divide-ash">
              <Row subject="Experience" now={`${troupe.xp_floor} XP, the troupe's XP floor`} book={`${BOOK_XP} XP`} />
            </ul>
          )}
          {starting.map((s) => (
            <SplatPart key={s.splat} label={s.label} split={starting.length > 1 || s.splat !== "vampire"}>
              {s.starting.map((c) => (
                <Row key={c.category} subject={c.category} now={c.text} book={c.book_text} />
              ))}
            </SplatPart>
          ))}
        </Card>
      )}

      {r.checks.length > 0 && (
        <Card title="Checks">
          <ul className="divide-y divide-ash">
            {r.checks.map((c) => (
              <Row
                key={c.rule}
                subject={
                  <>
                    {c.rule}
                    {c.page && <span className="text-mist"> {pageText(c.page)}</span>}
                  </>
                }
                note={c.own ? "the troupe's own check" : null}
                now={PLAYED[c.house] ?? c.house}
                book={c.own ? "Not in the book" : (PLAYED[c.strength] ?? c.strength)}
              />
            ))}
          </ul>
        </Card>
      )}

      {r.house_traits.length > 0 && (
        <Card
          title="House merits and flaws"
          actions={
            <Link to={`/rules?category=merits&troupe=${troupe.id}`} className="text-sm text-mist underline hover:text-parchment">
              See all merits
            </Link>
          }
        >
          <ul className="divide-y divide-ash">
            {r.house_traits.map((h) => (
              <li key={`${h.splat}/${h.category}/${h.name}`} className="flex flex-col gap-1 py-2.5 text-sm">
                <span className="text-parchment">
                  {h.name} ({h.points} {h.points === 1 ? "point" : "points"}, {h.kind})
                  <HouseMark label={h.label} />
                </span>
                <span className="text-xs text-mist">
                  {h.availability === "staff" ? "Given by the storytellers only." : "Available when building for the troupe."}
                  {h.availability === "building" && h.creation_only && " Only during character creation."}
                  {h.requirement && ` Requires ${h.requirement}.`}
                </span>
                {h.description && <p className="text-xs text-mist">{h.description}</p>}
                <HouseSummary summary={h.summary} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      {actions.length > 0 && (
        <Card title="Downtime actions">
          {actions.map((s) => (
            <SplatPart key={s.splat} label={s.label} split={actions.length > 1 || s.splat !== "vampire"}>
              {s.actions.map((a) => (
                <Row key={a.who} subject={a.who} now={a.amount_text} book={a.book_text ?? "None"} />
              ))}
            </SplatPart>
          ))}
        </Card>
      )}

      {r.other.length > 0 && (
        <Card title="Other house rules">
          <ul className="divide-y divide-ash">
            {r.other.map((o) => (
              <Row key={o.name} subject={o.name} now={o.text} book={o.book_text} />
            ))}
          </ul>
        </Card>
      )}

      <Card title="Backstories">
        <p className="text-sm">{BACKSTORY[r.backstory_mode] ?? r.backstory_mode}</p>
        <p className="mt-1 text-sm text-mist">
          {r.backstory_required
            ? "The storytellers approve it before the troupe accepts the character."
            : "The troupe can accept a character before its backstory is approved."}
        </p>
      </Card>

      {troupe.quests_enabled && (
        <Card title="Quests">
          <p className="text-sm">
            This troupe runs quests. Each character can ask for {troupe.quest_requests_per_cycle} {troupe.quest_requests_per_cycle === 1 ? "quest" : "quests"}{" "}
            each downtime cycle.
          </p>
        </Card>
      )}
    </div>
  );
}

/** One splat's part of a card: under its name when the troupe has rules for several. */
function SplatPart({ label, split, children }: { label: string; split: boolean; children: ReactNode }) {
  return (
    <section className="not-first:mt-4">
      {split && <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{label}</h3>}
      <ul className="divide-y divide-ash">{children}</ul>
    </section>
  );
}

/** A house rule: what it is about, how the troupe plays it, and how the book does. */
function Row({ subject, now, book, note }: { subject: ReactNode; now: string; book?: string | null; note?: string | null }) {
  return (
    <li className="flex flex-col gap-0.5 py-2.5 text-sm sm:flex-row sm:items-baseline sm:gap-4">
      <span className="min-w-0 flex-1">
        <span className="text-parchment">{subject}</span>
        {note && <span className="block text-xs text-mist">House rule: {note}</span>}
      </span>
      <span className="flex flex-col sm:items-end sm:text-right">
        <span className="text-gold">{now}</span>
        {book && <span className="text-xs text-mist">By the book: {book}</span>}
      </span>
    </li>
  );
}
