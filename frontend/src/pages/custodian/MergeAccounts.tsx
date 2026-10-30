import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { PlayerSummary } from "../../api/types";
import { AtHandle, PersonPicker } from "../../components/PersonPicker";
import { Button, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

type MergePreview = components["schemas"]["MergePreview"];

/**
 * The custodian merges two accounts of the same person (#272): pick the other
 * account, which one stays, and a reason, then confirm what moves. The other is
 * closed. It can't be undone.
 */
export function MergeAccounts({ person, onDone }: { person: PlayerSummary; onDone: () => void }) {
  const [other, setOther] = useState("");
  const [keepThis, setKeepThis] = useState(true);
  const [reason, setReason] = useState("");
  const otherHandle = other.trim().replace(/^@/, "");
  const keep = keepThis ? person.handle : otherHandle;
  const merge = keepThis ? otherHandle : person.handle;
  const review = useMutation({
    mutationFn: () => unwrap(api.GET("/api/accounts/merge", { params: { query: { keep, merge } } })),
  });
  const merging = useAction(async () => {
    await unwrap(api.POST("/api/accounts/merge", { body: { keep, merge, reason } }));
    onDone();
  });

  if (review.data) {
    return (
      <Confirm
        preview={review.data}
        reason={reason}
        merging={merging.isPending}
        error={merging.error}
        onMerge={() => merging.mutate(undefined)}
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
      <Field label="The same person's other account">
        <PersonPicker required value={other} onChange={setOther} />
      </Field>
      <fieldset className="flex flex-col gap-1 text-sm">
        <legend className="mb-1 text-mist">Which account stays?</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="merge-keep" checked={keepThis} onChange={() => setKeepThis(true)} />
          <span>
            {person.display_name} <AtHandle handle={person.handle} />
          </span>
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="merge-keep" checked={!keepThis} onChange={() => setKeepThis(false)} />
          <span>{otherHandle ? <AtHandle handle={otherHandle} /> : "The other account"}</span>
        </label>
      </fieldset>
      <Field label="Reason" hint="Kept in the audit log and the log of each troupe it touches, and told to the person and those troupes' lead storytellers.">
        <Textarea required rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={review.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={review.isPending || !otherHandle || !reason.trim()}>
          Continue
        </Button>
      </div>
    </form>
  );
}

/** What the merge will move and close, for the custodian to confirm, or why it can't be made now. */
function Confirm({
  preview: p,
  reason,
  merging,
  error,
  onMerge,
  onBack,
}: {
  preview: MergePreview;
  reason: string;
  merging: boolean;
  error: unknown;
  onMerge: () => void;
  onBack: () => void;
}) {
  const keep = `@${p.keep.handle}`;
  const gone = `@${p.merge.handle}`;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>
        Merge {p.merge.display_name} <AtHandle handle={p.merge.handle} /> into {p.keep.display_name} <AtHandle handle={p.keep.handle} />? This can't be undone.
      </p>
      <section>
        <h3 className="mb-1 text-mist">Moves to {keep}</h3>
        <ul className="list-disc space-y-1 pl-5">
          {p.characters.map((c) => (
            <li key={c.id}>
              {c.name}
              {c.retired && " (retired)"}
              {c.troupes.length > 0 && <span className="text-mist"> · {c.troupes.map((t) => t.name).join(", ")}</span>}
            </li>
          ))}
          {p.staff.map((s) => (
            <li key={s.troupe.id}>
              {s.troupe.name}: {s.summary}
            </li>
          ))}
          {p.sign_in.length > 0 && <li>Signing in with {p.sign_in.join(", ")}</li>}
          {p.settings.length > 0 && (
            <li>
              Its {p.settings.join(", ")}, as {keep} has none
            </li>
          )}
          {p.others.map((o) => (
            <li key={o}>{o}</li>
          ))}
          <li>
            {p.handles.map((h) => `@${h}`).join(", ")} will find {keep}, for good
          </li>
        </ul>
      </section>
      {p.also.length > 0 && (
        <section>
          <h3 className="mb-1 text-mist">Also</h3>
          <ul className="list-disc space-y-1 pl-5">
            {p.also.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </section>
      )}
      <p>
        {gone} is then closed: signed out everywhere, it can't sign in, and it isn't listed or found. Its email is kept for the record, but free for use. What
        it did stays as it was, shown as “{p.merge.display_name} (merged into {keep})”.
      </p>
      <p>Reason: {reason.trim()}</p>
      {p.refusals.map((r) => (
        <ErrorText key={r} error={r} />
      ))}
      <ErrorText error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" disabled={p.refusals.length > 0 || merging} onClick={onMerge}>
          Merge into {keep}
        </Button>
      </div>
    </div>
  );
}
