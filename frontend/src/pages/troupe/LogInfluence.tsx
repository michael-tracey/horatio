import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Loading } from "../../components/ui";
import { EntryForm } from "./InfluenceLogTab";

/**
 * The Log influence tool (#134) away from the log page: a button that opens it
 * over the page, with a character, and perhaps a cycle, filled in. For the
 * troupe's storytellers and assistant storytellers.
 */
export function LogInfluenceButton({
  troupeId,
  characterId,
  cycleId,
  label = "Log influence",
}: {
  troupeId: string;
  characterId?: string;
  cycleId?: string;
  /** What the button says to screen readers, where several sit on one page. */
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" aria-label={label} onClick={() => setOpen(true)}>
        Log influence
      </Button>
      <Dialog title="Log influence" wide open={open} onClose={() => setOpen(false)}>
        <LogInfluence troupeId={troupeId} characterId={characterId} cycleId={cycleId} onDone={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

function LogInfluence({ troupeId, characterId, cycleId, onDone }: { troupeId: string; characterId?: string; cycleId?: string; onDone: () => void }) {
  const choices = useQuery({
    queryKey: ["influence-choices", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-log/choices", { params: { path: { troupe_id: troupeId } } })),
  });
  if (choices.isPending) return <Loading />;
  if (choices.error) return <ErrorText error={choices.error} />;
  return <EntryForm troupeId={troupeId} choices={choices.data} characterId={characterId} cycleId={cycleId} onDone={onDone} />;
}
