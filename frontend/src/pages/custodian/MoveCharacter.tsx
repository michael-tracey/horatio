import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Dialog } from "../../components/Dialog";
import { AtHandle, PersonPicker } from "../../components/PersonPicker";
import { Button, Empty, ErrorText, Field, Loading, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { roleLabel } from "../troupe/roles";

type MovePreview = components["schemas"]["MovePreview"];

/**
 * The custodian gives a character to a different player (#271): pick the new
 * player and give a reason, then confirm what will happen. Only its player
 * changes; the character keeps its sheet, XP, history and troupes.
 */
export function MoveCharacter({
  characterId,
  characterName,
  playerId,
  onDone,
}: {
  characterId: string;
  characterName: string;
  playerId: string;
  onDone: () => void;
}) {
  const [handle, setHandle] = useState("");
  const [reason, setReason] = useState("");
  const player = useQuery({
    queryKey: ["player", playerId],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: playerId } } })),
  });
  const review = useMutation({
    mutationFn: () => unwrap(api.GET("/api/characters/{character_id}/move", { params: { path: { character_id: characterId }, query: { handle } } })),
  });
  const move = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/move", { params: { path: { character_id: characterId } }, body: { handle, reason } }));
    onDone();
  });

  if (review.data) {
    return (
      <Confirm
        preview={review.data}
        reason={reason}
        moving={move.isPending}
        error={move.error}
        onMove={() => move.mutate(undefined)}
        onBack={() => review.reset()}
      />
    );
  }
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        review.mutate();
      }}
    >
      <p className="text-sm">
        {characterName} is played by{" "}
        {player.data ? (
          <>
            {player.data.display_name} <AtHandle handle={player.data.handle} />
          </>
        ) : (
          "…"
        )}
        .
      </p>
      <Field label="New player">
        <PersonPicker required value={handle} onChange={setHandle} />
      </Field>
      <Field label="Reason" hint="Kept in the character's log, and told to both players and its home troupe's lead storyteller.">
        <Textarea required rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={review.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={review.isPending || !handle.trim() || !reason.trim()}>
          Continue
        </Button>
      </div>
    </form>
  );
}

/** What the move will do, for the custodian to confirm, or why it can't be made now. */
function Confirm({
  preview: p,
  reason,
  moving,
  error,
  onMove,
  onBack,
}: {
  preview: MovePreview;
  reason: string;
  moving: boolean;
  error: unknown;
  onMove: () => void;
  onBack: () => void;
}) {
  const from = `@${p.from_player.handle}`;
  const to = `@${p.to_player.handle}`;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>
        Move <strong>{p.character_name}</strong>
        {p.retired && " (retired)"} from {p.from_player.display_name} <AtHandle handle={p.from_player.handle} /> to {p.to_player.display_name}{" "}
        <AtHandle handle={p.to_player.handle} />?
      </p>
      <ul className="list-disc space-y-1 pl-5">
        <li>
          {p.home_troupe ? (
            <>
              Its home troupe is {p.home_troupe.name}
              {p.visiting.length > 0 && <>, and it visits {p.visiting.map((t) => t.name).join(", ")}</>}.
            </>
          ) : p.visiting.length > 0 ? (
            <>It has no home troupe, and visits {p.visiting.map((t) => t.name).join(", ")}.</>
          ) : (
            <>It is in no troupe.</>
          )}{" "}
          It stays in them.
        </li>
        <li>Its sheet, XP, history, titles and status go with it.</li>
        <li>
          {from} can no longer open it; {to} can, at once.
        </li>
        {p.staff_roles.map((s) => (
          <li key={s.troupe.id}>
            {to} is {s.role === "lead_storyteller" ? "the" : "a"} {roleLabel(s.role).toLowerCase()} of {s.troupe.name}.
          </li>
        ))}
        <li>Reason: {reason.trim()}</li>
      </ul>
      {p.open_requests.length > 0 && (
        <section>
          <h3 className="mb-1 text-mist">Waiting requests, which stay open for {to} to see or withdraw</h3>
          <ul className="list-disc space-y-1 pl-5">
            {p.open_requests.map((r, i) => (
              <li key={i}>
                {r.summary} ({r.troupe.name})
              </li>
            ))}
          </ul>
        </section>
      )}
      <ErrorText error={p.refusal} />
      <ErrorText error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" disabled={!!p.refusal || moving} onClick={onMove}>
          Move {p.character_name} to {to}
        </Button>
      </div>
    </div>
  );
}

/** A person's characters on the People tab, each with Move to another player. */
export function PersonCharacters({ playerId }: { playerId: string }) {
  const [moving, setMoving] = useState<{ id: string; name: string } | null>(null);
  const player = useQuery({
    queryKey: ["player", playerId],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: playerId } } })),
  });
  if (player.isPending) return <Loading />;
  if (player.error) return <ErrorText error={player.error} />;
  return (
    <>
      {player.data.characters.length ? (
        <ul className="divide-y divide-ash/50 text-sm">
          {player.data.characters.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1.5">
              <Link to={`/characters/${c.id}`} className="hover:text-gold">
                {c.name}{" "}
                <span className="text-xs text-mist">
                  {c.home_troupe ?? "no home troupe"}
                  {c.retired && " · retired"}
                </span>
              </Link>
              <Button type="button" variant="ghost" className="min-h-8 px-2 text-xs" aria-label={`Move ${c.name} to another player`} onClick={() => setMoving(c)}>
                Move…
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>No characters.</Empty>
      )}
      <Dialog title={`Move ${moving?.name ?? ""} to another player`} open={!!moving} onClose={() => setMoving(null)}>
        {moving && <MoveCharacter characterId={moving.id} characterName={moving.name} playerId={playerId} onDone={() => setMoving(null)} />}
      </Dialog>
    </>
  );
}
