import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CalendarLinks, GameRsvpsOut, TroupeOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { AtHandle } from "../../components/PersonPicker";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { ANSWERS, answeredText, byAnswer, countsText, webcal, type Answer } from "./games";

/**
 * The troupe's games still to come, for its members: each says whether they are
 * coming, and sees how many are; its staff also see who (issue #420). And the way
 * to put the troupe's games and downtime dates in their own calendar.
 */
export function GamesCard({ troupe, canAddGames }: { troupe: TroupeOut; canAddGames: boolean }) {
  const [subscribing, setSubscribing] = useState(false);
  const games = useQuery({
    queryKey: ["troupe-games", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/games", { params: { path: { troupe_id: troupe.id } } })),
  });
  return (
    <Card
      title="Games"
      className="md:col-span-2"
      actions={
        <Button variant="secondary" onClick={() => setSubscribing(true)}>
          Subscribe to the calendar
        </Button>
      }
    >
      {games.isPending ? (
        <Loading />
      ) : games.error ? (
        <ErrorText error={games.error} />
      ) : games.data.length === 0 ? (
        <EmptyState
          title="No games planned yet."
          action={
            canAddGames && (
              <Link to={`/troupes/${troupe.id}/profile`} className="text-sm text-gold underline">
                Add games on the Profile tab
              </Link>
            )
          }
        >
          When there is one, say here whether you're coming.
        </EmptyState>
      ) : (
        <ul className="flex flex-col divide-y divide-ash" aria-label="Games to come">
          {games.data.map((g) => (
            <GameRow key={g.id} troupeId={troupe.id} game={g} />
          ))}
        </ul>
      )}
      <Dialog title="Subscribe to the calendar" open={subscribing} onClose={() => setSubscribing(false)} phoneFull>
        <Subscribe troupe={troupe} />
      </Dialog>
    </Card>
  );
}

/** One game: when, your answer, how many said each, and for staff, who. */
function GameRow({ troupeId, game }: { troupeId: string; game: GameRsvpsOut }) {
  const dates = useDates();
  const toast = useToast();
  const when = dates.gameStart(game.starts_at);
  const path = { params: { path: { troupe_id: troupeId, game_id: game.id } } };
  const answer = useAction(
    async (chosen: Answer | null) => {
      await unwrap(
        chosen === null
          ? api.DELETE("/api/troupes/{troupe_id}/games/{game_id}/rsvp", path)
          : api.PUT("/api/troupes/{troupe_id}/games/{game_id}/rsvp", { ...path, body: { answer: chosen } }),
      );
      toast({ message: answeredText(chosen, when) });
    },
    [["troupe-games", troupeId]],
  );
  // The answer being sent shows at once.
  const mine = answer.isPending ? answer.variables : game.my_answer;

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <time dateTime={game.starts_at} className="font-medium text-parchment">
          {dates.game(game.starts_at, game.ends_at)}
        </time>
        <span className="text-sm text-mist">{countsText(game)}</span>
      </div>
      <div role="group" aria-label={`Are you coming on ${when}?`} className="grid grid-cols-3 gap-2 sm:flex">
        {ANSWERS.map((a) => {
          const on = mine === a.answer;
          return (
            <button
              key={a.answer}
              type="button"
              aria-pressed={on}
              disabled={answer.isPending}
              // Tapping your answer again takes it back.
              onClick={() => answer.mutate(on ? null : a.answer)}
              className={`min-h-10 rounded-md border px-3 text-sm transition-colors pointer-coarse:min-h-11 disabled:opacity-60 ${
                on ? "border-gold bg-gold/15 text-gold" : "border-line text-parchment hover:border-mist"
              }`}
            >
              {a.label}
            </button>
          );
        })}
      </div>
      <ErrorText error={answer.error} />
      {game.answers && game.answers.length > 0 && <WhoIsComing game={game} />}
    </li>
  );
}

/** For staff: who said what, with the characters each plays here. */
function WhoIsComing({ game }: { game: GameRsvpsOut }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer py-1 text-mist hover:text-parchment pointer-coarse:py-2.5">See who answered</summary>
      <div className="mt-1 flex flex-col gap-2">
        {byAnswer(game.answers ?? []).map((group) => (
          <div key={group.answer}>
            <h3 className="text-xs text-mist">
              {group.label} ({group.people.length})
            </h3>
            <ul aria-label={group.label} className="flex flex-col gap-0.5">
              {group.people.map((r) => (
                <li key={r.person.id}>
                  <Link to={`/players/${r.person.id}`} className="hover:text-gold">
                    {r.person.display_name}
                  </Link>{" "}
                  <AtHandle handle={r.person.handle} />
                  {r.characters.length > 0 && <span className="text-mist"> · {r.characters.join(", ")}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

/** The person's calendar links, this troupe's and all their troupes', with how to subscribe in the common apps. */
function Subscribe({ troupe }: { troupe: TroupeOut }) {
  const links = useQuery({
    queryKey: ["calendar-links", troupe.id],
    queryFn: () => unwrap(api.GET("/api/calendar/links", { params: { query: { troupe_id: troupe.id } } })),
  });
  if (links.isPending) return <Loading />;
  if (links.error) return <ErrorText error={links.error} />;
  return (
    <div className="flex flex-col gap-5 text-sm">
      <p>Put the troupe's games and downtime dates in your own calendar. It keeps itself up to date.</p>
      <LinkRow title={`${troupe.name} only`} troupeId={troupe.id} personal={false} link={links.data.troupe} />
      <LinkRow title="All your troupes" troupeId={troupe.id} personal link={links.data.personal} />
      <section aria-labelledby="calendar-help" className="flex flex-col gap-2">
        <h3 id="calendar-help" className="font-display text-parchment">
          How to subscribe
        </h3>
        <dl className="flex flex-col gap-2">
          <div>
            <dt className="text-parchment">Google Calendar</dt>
            <dd className="text-mist">On a computer, beside "Other calendars" choose +, then "From URL", and paste the link. It shows on your phone too.</dd>
          </div>
          <div>
            <dt className="text-parchment">Apple Calendar</dt>
            <dd className="text-mist">On an iPhone or Mac, choose "Open in your calendar app", then Subscribe.</dd>
          </div>
          <div>
            <dt className="text-parchment">Outlook</dt>
            <dd className="text-mist">Choose "Add calendar", then "Subscribe from web", and paste the link.</dd>
          </div>
        </dl>
        <p className="text-xs text-mist">Calendar apps look for changes every few hours, so a new game can take a while to show.</p>
      </section>
    </div>
  );
}

/** One calendar link, the troupe's or (`personal`) all the person's troupes': made when first asked for, then copied, opened or reset. */
function LinkRow({ title, troupeId, personal, link }: { title: string; troupeId: string; personal: boolean; link: CalendarLinks["troupe"] }) {
  const [confirming, setConfirming] = useState(false);
  // Said here, not in a toast, which would be behind the dialog.
  const [said, setSaid] = useState("");
  const make = useAction(
    async () => {
      await unwrap(api.POST("/api/calendar/links", { body: { troupe_id: personal ? null : troupeId } }));
      setSaid(link ? "New link made. The old one no longer works." : "");
      setConfirming(false);
    },
    [["calendar-links", troupeId]],
  );
  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setSaid("Copied.");
    } catch {
      // No clipboard here (an insecure page, or refused): the link is there to copy by hand.
    }
  };

  return (
    <section aria-label={title} className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <h3 className="font-display text-parchment">{title}</h3>
      {link ? (
        <>
          <span className="font-mono text-xs break-all select-all">{link.url}</span>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => void copy()}>
              Copy the link
            </Button>
            <a href={webcal(link.url)} className="inline-flex min-h-10 items-center rounded-md border border-ash px-4 text-sm text-parchment hover:border-mist">
              Open in your calendar app
            </a>
          </div>
          <p className="text-xs text-mist">Keep it to yourself: anyone with it can see these dates.</p>
          {confirming ? (
            <div className="flex flex-col gap-2 rounded-md border border-blood/60 p-2">
              <p className="text-xs">The old link stops working, and calendars subscribed with it stop updating.</p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="danger" disabled={make.isPending} onClick={() => make.mutate(undefined)}>
                  Reset the link
                </Button>
                <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                  Keep it
                </Button>
              </div>
            </div>
          ) : (
            <Button type="button" variant="ghost" className="self-start px-0" onClick={() => setConfirming(true)}>
              Reset the link…
            </Button>
          )}
        </>
      ) : (
        <Button type="button" variant="secondary" className="self-start" disabled={make.isPending} onClick={() => make.mutate(undefined)}>
          Get the link
        </Button>
      )}
      <p role="status" className="text-xs text-gold empty:hidden">
        {said}
      </p>
      <ErrorText error={make.error} />
    </section>
  );
}
