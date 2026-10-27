import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

type Reason = "final_death" | "off_field" | "inactive";

/** Why a character left, in the words the Who's Who shows (horatio.leaving). */
const REASONS: { key: Reason; name: string; about: string }[] = [
  { key: "final_death", name: "Final Death", about: "The character is dead." },
  { key: "off_field", name: "Off-field", about: "Alive, but away from the domain." },
  { key: "inactive", name: "Inactive", about: "Its player stopped playing it. It says nothing in game." },
];

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
}: {
  character: CharacterOut;
  initial: { reason: Reason | null; listed: boolean | null };
  submit: string;
  pending: boolean;
  error: unknown;
  onSubmit: (body: LeavingBody) => void;
  onCancel: () => void;
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
  const retire = useAction((body: LeavingBody) =>
    unwrap(api.POST("/api/characters/{character_id}/retire", { params: { path: { character_id: character.id } }, body })),
  );
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        A retired character is hidden from everyday lists and out of all downtimes, but kept with its full history. Its sheet can no longer change.
      </p>
      <LeavingForm
        character={character}
        initial={{ reason: null, listed: null }}
        submit={`Retire ${character.name}`}
        pending={retire.isPending}
        error={retire.error}
        onSubmit={(body) => retire.mutate(body, { onSuccess: onDone })}
        onCancel={onDone}
      />
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
