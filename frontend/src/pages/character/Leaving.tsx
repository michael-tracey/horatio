import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction, useMe } from "../../hooks";
import { abilities } from "../troupe/roles";

type Reason = "final_death" | "off_field" | "inactive";

/** Why a character left, in the words the Who's Who shows (horatio.leaving). */
const REASONS: { key: Reason; name: string; about: string }[] = [
  { key: "final_death", name: "Final Death", about: "The character is dead." },
  { key: "off_field", name: "Off-field", about: "Alive, but away from the domain." },
  { key: "inactive", name: "Inactive", about: "Its player stopped playing it. It says nothing in game." },
];

/** "Prince", "Prince and Harpy", "Prince, Harpy and Whip". */
const andList = (names: string[]) => new Intl.ListFormat("en-GB", { type: "conjunction" }).format(names);

type LeavingBody = { reason: Reason; note: string; listed: boolean };

/** Listed under "No longer with us" unless the player only stopped playing it. */
function listedByDefault(reason: Reason): boolean {
  return reason !== "inactive";
}

/**
 * The reason, a note for the log, and whether the Who's Who lists the character.
 * The listing follows the reason (Inactive unlisted) until someone ticks it.
 */
function LeavingForm({
  character,
  initial,
  submit,
  pending,
  error,
  onSubmit,
  onCancel,
  children,
}: {
  character: CharacterOut;
  initial: { reason: Reason | null; listed: boolean | null };
  submit: string;
  pending: boolean;
  error: unknown;
  onSubmit: (body: LeavingBody) => void;
  onCancel: () => void;
  /** More choices, after the listing. */
  children?: ReactNode;
}) {
  const [reason, setReason] = useState<Reason | null>(initial.reason);
  const [note, setNote] = useState("");
  const [listed, setListed] = useState<boolean | null>(initial.listed);
  const shown = listed ?? (reason ? listedByDefault(reason) : false);
  return (
    <form
      aria-label="Why it left"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason) onSubmit({ reason, note, listed: shown });
      }}
    >
      <fieldset className="flex flex-col gap-2 text-sm">
        <legend className="mb-1 text-mist">Why {character.name} left</legend>
        {REASONS.map((r) => (
          <label key={r.key} className="flex items-start gap-2">
            <input type="radio" name="leaving-reason" className="mt-1" checked={reason === r.key} onChange={() => setReason(r.key)} />
            <span>
              {r.name}
              <span className="block text-xs text-mist">{r.about}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <Field label="Note (optional)" hint="Goes in the character's log, which its player and staff see.">
        <Textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={shown} disabled={!reason} onChange={(e) => setListed(e.target.checked)} />
        <span>
          List {character.name} under “No longer with us” on the Who's Who
          <span className="block text-xs text-mist">
            Its troupes' players and staff see its name, clan, social age, player and why it left.
            {reason === "inactive" && " Inactive says nothing in game, so it is unlisted unless you choose."}
          </span>
        </span>
      </label>
      {children}
      <ErrorText error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!reason || pending}>
          {submit}
        </Button>
      </div>
    </form>
  );
}

/** Retiring, from the character's ⋯ menu: hidden from everyday lists and out of all downtimes, kept with its history. */
export function RetireCharacter({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const retire = useAction((body: LeavingBody & { remembrances: boolean }) =>
    unwrap(api.POST("/api/characters/{character_id}/retire", { params: { path: { character_id: character.id } }, body })),
  );
  // Its home troupe's Remembrances (#471): its running staff open them; its player asks.
  const homeId = character.kind === "pc" ? character.home_troupe_id : null;
  const home = useQuery({
    queryKey: ["troupe", homeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: homeId! } } })),
    enabled: !!homeId,
  });
  // The titles it holds, in each troupe: retiring gives them all up (horatio.titles).
  const troupes = useQuery({
    queryKey: ["memberships", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/troupes", { params: { path: { character_id: character.id } } })),
  });
  const titled = (troupes.data ?? []).filter((t) => t.titles.length > 0);
  const me = useMe();
  const [remember, setRemember] = useState(false);
  const offered = !!home.data?.remembrances && !home.data.archived;
  const opens = !!home.data && abilities(home.data.my_role, me.data?.is_custodian ?? false).running;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        A retired character is hidden from everyday lists and out of all downtimes, but kept with its full history. Its sheet can no longer change.
      </p>
      {titled.length > 0 && (
        <p className="text-sm" role="note" aria-label="Titles given up">
          {titled.map((t) => `${character.name} holds ${andList(t.titles)} in ${t.troupe_name}. `)}
          Retiring gives {titled.flatMap((t) => t.titles).length > 1 ? "them" : "it"} up.
        </p>
      )}
      <LeavingForm
        character={character}
        initial={{ reason: null, listed: null }}
        submit={`Retire ${character.name}`}
        pending={retire.isPending}
        error={retire.error}
        onSubmit={(body) => retire.mutate({ ...body, remembrances: offered && remember }, { onSuccess: onDone })}
        onCancel={onDone}
      >
        {offered && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>
              {opens ? "Open remembrances in the next downtime" : "Ask the storytellers to open remembrances in the next downtime"}
              <span className="block text-xs text-mist">
                Everyone in {home.data!.name} is asked for a memory of {character.name}. The storytellers read them first, and publish them without names.
              </span>
            </span>
          </label>
        )}
      </LeavingForm>
    </div>
  );
}

/** On a retired character's page: why it left, and whether the Who's Who lists it; its player or its home troupe's staff can change them. */
export function LeavingCard({ character, canChange }: { character: CharacterOut; canChange: boolean }) {
  const [changing, setChanging] = useState(false);
  const change = useAction((body: LeavingBody) =>
    unwrap(api.PUT("/api/characters/{character_id}/leaving", { params: { path: { character_id: character.id } }, body })),
  );
  const reason = REASONS.find((r) => r.key === character.left_reason);
  return (
    <Card dense className="mb-4" title="Retired">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p>
          {reason ? `Why ${character.name} left: ${reason.name}.` : `${character.name} was retired without a reason.`}{" "}
          <span className="text-mist">{character.left_listed ? "Listed under “No longer with us” on the Who's Who." : "Not on the Who's Who."}</span>
        </p>
        {canChange && (
          <Button variant="secondary" onClick={() => setChanging(true)}>
            {reason ? "Change…" : "Give a reason…"}
          </Button>
        )}
      </div>
      <Dialog title={`Why ${character.name} left`} open={changing} onClose={() => setChanging(false)}>
        <LeavingForm
          character={character}
          initial={{ reason: reason?.key ?? null, listed: reason ? character.left_listed : null }}
          submit="Save"
          pending={change.isPending}
          error={change.error}
          onSubmit={(body) => change.mutate(body, { onSuccess: () => setChanging(false) })}
          onCancel={() => setChanging(false)}
        />
      </Dialog>
    </Card>
  );
}
