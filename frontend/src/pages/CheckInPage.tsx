import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { CheckInOffer } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Button, Card, ErrorText, Field, Input, Loading, PageTitle } from "../components/ui";
import { useDates } from "../dates";
import { useAction } from "../hooks";
import { checkInPath, tidyCode } from "./troupe/checkin";

/**
 * Checking in at a game's door (issue #421): the page a door's QR code opens, or
 * where its code is typed. A signed-out person signs in first and comes back here.
 */
export function CheckInPage() {
  const { code = "" } = useParams();
  const offer = useQuery({
    queryKey: ["check-in", code],
    queryFn: () => unwrap(api.GET("/api/checkin/{code}", { params: { path: { code } } })),
    enabled: !!code,
    retry: false,
  });
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      <PageTitle>Check in</PageTitle>
      {!code ? (
        <CodeForm />
      ) : offer.isPending ? (
        <Loading />
      ) : offer.error ? (
        <>
          <ErrorText error={offer.error} />
          <CodeForm />
        </>
      ) : (
        <Card>
          <CheckInForm offer={offer.data} />
        </Card>
      )}
    </div>
  );
}

/** The door's code, typed. */
function CodeForm() {
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  return (
    <Card>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (tidyCode(typed)) navigate(checkInPath(tidyCode(typed)));
        }}
      >
        <Field label="Code from the door" hint="Six letters and numbers, such as ABC 234.">
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            maxLength={12}
            className="font-mono text-lg tracking-widest uppercase"
          />
        </Field>
        <Button type="submit" className="self-start" disabled={!tidyCode(typed)}>
          Go on
        </Button>
      </form>
    </Card>
  );
}

/**
 * Pick the character you're playing tonight and say whether it had a full day's
 * rest, then check in: the night starts on its Play View, which opens.
 */
export function CheckInForm({ offer }: { offer: CheckInOffer }) {
  const dates = useDates();
  const navigate = useNavigate();
  const waiting = offer.characters.filter((c) => !c.checked_in);
  const [chosen, setChosen] = useState(waiting[0]?.id ?? "");
  const [rested, setRested] = useState(true);
  const go = useAction(async () => {
    const done = await unwrap(
      api.POST("/api/troupes/{troupe_id}/games/{game_id}/attendance", {
        params: { path: { troupe_id: offer.troupe_id, game_id: offer.game_id } },
        body: { character_id: chosen, rested },
      }),
    );
    // The Play View opening is the answer: a toast would go with the page it was on.
    navigate(`/play/characters/${done.character_id}`);
  });

  const heading = (
    <p className="text-sm">
      <span className="font-display text-gold">{offer.troupe_name}</span>
      <br />
      <time dateTime={offer.starts_at} className="text-mist">
        {dates.game(offer.starts_at, offer.ends_at)}
      </time>
    </p>
  );
  if (offer.characters.length === 0)
    return (
      <div className="flex flex-col gap-3">
        {heading}
        <EmptyState title={`You have no character in ${offer.troupe_name}.`}>Ask the storytellers at the door to check you in.</EmptyState>
      </div>
    );

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (chosen) go.mutate(undefined);
      }}
    >
      {heading}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm text-parchment">Who are you playing tonight?</legend>
        {offer.characters.map((c) =>
          c.checked_in ? (
            <p key={c.id} className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-ash px-3 text-sm">
              <span>
                {c.name} <span className="text-mist">· checked in</span>
              </span>
              <Link to={`/play/characters/${c.id}`} className="text-gold underline">
                Open the Play View
              </Link>
            </p>
          ) : (
            <label
              key={c.id}
              className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-md border px-3 text-sm ${chosen === c.id ? "border-gold bg-gold/10" : "border-line"}`}
            >
              <input type="radio" name="character" value={c.id} checked={chosen === c.id} onChange={() => setChosen(c.id)} />
              {c.name}
            </label>
          ),
        )}
      </fieldset>
      {waiting.length > 0 && (
        <>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1" checked={rested} onChange={(e) => setRested(e.target.checked)} />
            <span>
              A full day's rest since the last game
              <span className="block text-xs text-mist">
                Willpower starts full after one (MET: VtM core, p. 288). Untick this and it starts where the last game left it.
              </span>
            </span>
          </label>
          <Button type="submit" className="min-h-12 text-base" disabled={!chosen || go.isPending}>
            Check in{chosen ? ` ${offer.characters.find((c) => c.id === chosen)?.name ?? ""}` : ""}
          </Button>
        </>
      )}
      <ErrorText error={go.error} />
    </form>
  );
}
