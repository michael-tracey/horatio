import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { OtherOut, SeenOut } from "../../api/types";
import { Pronouns } from "../../components/PronounsInput";
import { Badge, Button, ErrorText, Input } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { endingText } from "../character/status";
import { leadershipOf, matching, shownSeen } from "./others";
import { tapId, type Shown } from "./tracker";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const GROUPS = [
  { type: "Negative", title: "Negative" },
  { type: "Abiding", title: "Abiding" },
  { type: "Innate", title: "Innate" },
  { type: "Fleeting", title: "Fleeting" },
] as const;

/**
 * Others at this game, on the Status tab (MET: VTM p. 310): the troupe's characters,
 * found by name. Of the character's own sect, each one's status as it carries it
 * into its game, spent or not; a fleeting status's patron, where and story learned
 * with a Leadership use, with Undo; and negative status, which is public, in full.
 * Of another sect, only the name and sect.
 */
export function Others({ view, undo, online }: { view: Shown; undo: (tapId: string) => void; online: boolean }) {
  const characterId = view.character_id;
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const others = useQuery({
    queryKey: ["play-others", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play/others", { params: { path: { character_id: characterId } } })),
    enabled: online,
  });
  const found = matching(others.data ?? [], query);
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3" aria-labelledby="others-heading">
      <h2 id="others-heading" className="mb-2 text-base text-gold">
        Others at this game
      </h2>
      {picked ? (
        <OtherStatus view={view} otherId={picked} undo={undo} online={online} onBack={() => setPicked(null)} />
      ) : (
        <>
          <p className="mb-2 text-xs text-mist">
            Every Accepted member of your sect knows the status of the others. Leadership learns where a fleeting status came from: one a game for each dot.
          </p>
          <Input aria-label="Find a character" placeholder="Find a character" value={query} onChange={(e) => setQuery(e.target.value)} />
          {!online && <p className="mt-2 text-xs text-mist">Seeing others needs a connection.</p>}
          {others.isPending && online && <p className="mt-2 text-sm text-mist">Loading…</p>}
          <ErrorText error={others.error} />
          {others.data && found.length === 0 && <p className="mt-2 text-sm text-mist">{query ? "No one by that name." : "No one else in the troupe."}</p>}
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {found.map((o) => (
              <li key={o.character_id}>
                <button
                  type="button"
                  onClick={() => setPicked(o.character_id)}
                  className="flex min-h-12 w-full flex-col items-start rounded-md border border-ash bg-night px-3 py-2 text-left hover:border-mist"
                >
                  <span className="text-parchment">
                    {o.name}
                    <Pronouns pronouns={o.pronouns} />
                  </span>
                  <span className="text-xs text-mist">{sectLine(o)}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** "Camarilla · Prince", or the sect alone. */
function sectLine(o: OtherOut): string {
  return [o.sect ?? "No sect", ...o.titles].join(" · ");
}

function OtherStatus({ view, otherId, undo, online, onBack }: { view: Shown; otherId: string; undo: (tapId: string) => void; online: boolean; onBack: () => void }) {
  const characterId = view.character_id;
  // Asked again whenever the server has another tap of this game's, such as an undone learning.
  const saved = view.log.filter((e) => !e.pending).length;
  const path = { params: { path: { character_id: characterId, other_id: otherId } } };
  const shown = useQuery({
    queryKey: ["play-others", characterId, otherId, saved],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play/others/{other_id}", path)),
    placeholderData: keepPreviousData,
    // What the other spends shows as the Play View's own taps do.
    refetchInterval: 15_000,
    enabled: online,
  });
  const learn = useAction(async (key: string) =>
    unwrap(api.POST("/api/characters/{character_id}/play/others/{other_id}/learn", { ...path, body: { id: tapId(), key } })),
  );
  const remove = useAction(async (heldId: string) =>
    unwrap(
      api.POST("/api/characters/{character_id}/play/others/{other_id}/status/{held_id}/remove", {
        params: { path: { character_id: characterId, other_id: otherId, held_id: heldId } },
      }),
    ),
  );
  const leadership = leadershipOf(view.expendables);
  // Learning and removing refresh this (useAction), with the Play View's Leadership.
  const data = shown.data;
  const other = data?.other;
  return (
    <div className="flex flex-col gap-2">
      <Button variant="ghost" className="self-start" onClick={onBack}>
        ← Everyone
      </Button>
      {!online && <p className="text-xs text-mist">Seeing others needs a connection.</p>}
      {shown.isPending && online && <p className="text-sm text-mist">Loading…</p>}
      <ErrorText error={shown.error} />
      {other && (
        <>
          <h3 className="text-lg text-parchment">
            {other.name}
            <Pronouns pronouns={other.pronouns} className="text-sm text-mist" />
          </h3>
          {data.troupe_id && (
            <Link to={`/troupes/${data.troupe_id}/whos-who#c-${other.character_id}`} className="self-start text-sm text-mist underline hover:text-gold">
              {other.name} on the Who’s Who
            </Link>
          )}
          {data.status === null ? (
            <p className="text-sm">
              {other.sect ?? "No sect"}
              <span className="text-mist">. Only {other.sect ? `the ${other.sect}’s own know` : "a sect’s own know"} their status.</span>
            </p>
          ) : (
            <>
              <p className="text-sm">
                {other.accepted} by the {other.sect}
                {other.titles.length > 0 && <span className="text-mist"> · {other.titles.join(", ")}</span>}
              </p>
              <p className="text-xs text-mist">
                {leadership
                  ? `Leadership: ${leadership.left} of ${leadership.uses} left this game, to learn where a fleeting status came from.`
                  : "Without Leadership, you know their status but not where it came from (MET: VTM p. 310)."}
              </p>
              {data.status.length === 0 && <p className="text-sm text-mist">No status at this game.</p>}
              {GROUPS.map((g) => {
                const items = data.status!.filter((s) => s.type === g.type).map((s) => shownSeen(s, view.log));
                if (items.length === 0) return null;
                return (
                  <div key={g.type}>
                    <h4 className="text-xs tracking-wide text-gold uppercase">{g.title}</h4>
                    <ul className="divide-y divide-ash">
                      {items.map((s) => (
                        <SeenRow
                          key={s.key}
                          seen={s}
                          learn={leadership && s.learnable && !s.known ? () => learn.mutate(s.key) : undefined}
                          canLearn={online && !learn.isPending && (leadership?.left ?? 0) > 0}
                          undo={s.learned_by ? () => undo(s.learned_by!) : undefined}
                          remove={s.removable && s.held_id ? () => remove.mutate(s.held_id!) : undefined}
                          online={online}
                        />
                      ))}
                    </ul>
                  </div>
                );
              })}
            </>
          )}
        </>
      )}
      <ErrorText error={learn.error ?? remove.error} />
    </div>
  );
}

function SeenRow({
  seen: s,
  learn,
  canLearn,
  undo,
  remove,
  online,
}: {
  seen: SeenOut;
  learn?: () => void;
  canLearn: boolean;
  undo?: () => void;
  remove?: () => void;
  online: boolean;
}) {
  const dates = useDates();
  const actions: ReactNode[] = [];
  if (learn)
    actions.push(
      <Button key="learn" variant="secondary" className="min-h-10" disabled={!canLearn} aria-label={`Learn about ${s.name}`} onClick={learn}>
        Learn about this status
      </Button>,
    );
  if (undo)
    actions.push(
      <Button key="undo" variant="ghost" className="min-h-10" aria-label={`Undo learning about ${s.name}`} onClick={undo}>
        Undo
      </Button>,
    );
  if (remove)
    actions.push(
      <Button key="remove" variant="ghost" className="min-h-10" disabled={!online} aria-label={`Remove ${s.name}`} onClick={remove}>
        Remove
      </Button>,
    );
  return (
    <li className="flex flex-wrap items-start gap-2 py-2">
      <div className={cx("min-w-0 flex-1 text-sm", s.spent && "opacity-60")}>
        <p>
          <span className={cx("text-parchment", s.spent && "line-through")}>{s.name}</span>
          {s.spent && (
            <span className="ml-2">
              <Badge>Spent</Badge>
            </span>
          )}
        </p>
        {s.known && s.patron && (
          <p className="text-xs text-mist">
            From {s.patron}
            {s.place && `, at ${s.place}`}
          </p>
        )}
        {s.known && s.story && <p className="text-xs text-mist">{s.story}</p>}
        {s.ending && <p className="text-xs text-gold">{endingText(s.ending, dates.day)}.</p>}
      </div>
      {actions.length > 0 && <span className="flex flex-wrap items-center gap-2">{actions}</span>}
    </li>
  );
}
