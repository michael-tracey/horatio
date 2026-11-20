import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { useDates } from "../../dates";
import { useSeenUpTo } from "./resultsSeen";
import { GROUPS, shown, sinceText, stepText, toneOf, type Step } from "./nextSteps";

/** What is next for each of the player's characters, for the Characters page: one request for them all. */
export function useNextSteps() {
  return useQuery({ queryKey: ["characters-next"], queryFn: () => unwrap(api.GET("/api/characters/next")) });
}

/**
 * Next for this character (#1051), at the top of its page for its player: what is
 * theirs to do, what waits on staff and since when, and what is coming up, each a
 * link to where it is done. Hidden when nothing is next. On a phone the groups stack.
 */
export function NextForCharacter({ characterId }: { characterId: string }) {
  const next = useQuery({
    queryKey: ["character-next", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/next", { params: { path: { character_id: characterId } } })),
  });
  const seen = useSeenUpTo(characterId);
  const steps = shown(next.data?.steps, seen);
  if (!steps.length) return null;
  return (
    <section aria-label="Next for this character" className="mb-4 rounded-lg border border-gold/40 bg-dusk p-4 sm:mb-6">
      <h2 className="mb-2 text-lg text-gold">Next for this character</h2>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-x-10">
        {GROUPS.map(({ who, heading }) => {
          const these = steps.filter((s) => s.who === who);
          if (!these.length) return null;
          return (
            <div key={who} className="min-w-0">
              <h3 className="text-xs tracking-wide text-mist uppercase">{heading}</h3>
              <ul aria-label={heading} className="mt-1 flex flex-col gap-1 text-sm">
                {these.map((s) => (
                  <li key={`${s.kind} ${s.link}`}>
                    <StepLink step={s} />
                    <Since step={s} />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/**
 * A character's steps on the Characters page, under its name: what is the player's
 * first, then what waits on staff, then what is coming up, each group on a line of its
 * own that wraps on a phone. Nothing when nothing is next.
 */
export function NextLine({ steps, seen, className = "" }: { steps: Step[] | undefined; seen: string | null; className?: string }) {
  const listed = shown(steps, seen);
  if (!listed.length) return null;
  return (
    <ul aria-label="Next" className={`flex flex-col gap-0.5 text-sm ${className}`}>
      {GROUPS.map(({ who, heading }) => {
        const these = listed.filter((s) => s.who === who);
        if (!these.length) return null;
        return (
          <li key={who} className="min-w-0">
            {who !== "player" && <span className="text-mist">{heading}: </span>}
            {these.map((s, i) => (
              <span key={`${s.kind} ${s.link}`}>
                {i > 0 && <span className="text-mist"> · </span>}
                <StepLink step={s} />
                <Since step={s} />
              </span>
            ))}
          </li>
        );
      })}
    </ul>
  );
}

function StepLink({ step }: { step: Step }) {
  const dates = useDates();
  return (
    <Link to={step.link} className={`${toneOf(step)} underline decoration-ash underline-offset-2 hover:text-gold hover:decoration-gold`}>
      {stepText(step, dates)}
    </Link>
  );
}

function Since({ step }: { step: Step }) {
  const dates = useDates();
  const since = sinceText(step, dates);
  return since && <span className="whitespace-nowrap text-mist">, {since}</span>;
}
