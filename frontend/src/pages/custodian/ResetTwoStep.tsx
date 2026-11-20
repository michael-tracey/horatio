import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * The custodian resetting someone's two-step sign-in (#1057), when they've lost their
 * authenticator app and their recovery codes: every second step goes, and their
 * password alone signs them in until they set one up again. Kept in the audit log for
 * good, with the reason, and they're told.
 */
export function ResetTwoStep({ person, onDone }: { person: { id: string; display_name: string }; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const reset = useAction(async () => {
    await unwrap(api.POST("/api/two-step/reset/{user_id}", { params: { path: { user_id: person.id } }, body: { reason } }));
    onDone();
  }, [["players"]]);
  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        reset.mutate(undefined);
      }}
    >
      <p className="text-mist">
        Take away {person.display_name}'s passkeys, authenticator app and recovery codes, so their password alone signs them in until they set it up again. Do this only once you're sure it's them asking.
        They're told, with your reason.
      </p>
      <Field label="Why">
        <Textarea required rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={reset.error} />
      <Button type="submit" variant="danger" className="self-start" disabled={reset.isPending}>
        Reset two-step sign-in
      </Button>
    </form>
  );
}
