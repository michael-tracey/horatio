import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { PlayerSummary } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

/** "View as" on People: see Horatio as the person sees it, read-only, for up to 30
 * minutes, saying why. Never another custodian: People offers it only for others. */
export function ViewAs({ person, open, onClose }: { person: PlayerSummary; open: boolean; onClose: () => void }) {
  return (
    <Dialog title={`View as @${person.handle}`} open={open} onClose={onClose}>
      <StartViewing person={person} />
    </Dialog>
  );
}

function StartViewing({ person }: { person: PlayerSummary }) {
  const [reason, setReason] = useState("");
  const start = useAction(async () => {
    await unwrap(api.POST("/api/players/{user_id}/view-as", { params: { path: { user_id: person.id } }, body: { reason } }));
    // A fresh start, so nothing of the custodian's own stays on screen.
    window.location.assign("/characters");
  });
  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        start.mutate(undefined);
      }}
    >
      <p className="text-mist">
        See Horatio as {person.display_name} sees it, with their permissions, for up to 30 minutes. Nothing can be changed while you do. They're told, with
        your reason, and it goes in the audit log.
      </p>
      <Field label="Reason">
        <Textarea rows={3} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Can't find their downtime" />
      </Field>
      <ErrorText error={start.error} />
      <Button type="submit" disabled={start.isPending || !reason.trim()} className="self-start">
        Start viewing
      </Button>
    </form>
  );
}
