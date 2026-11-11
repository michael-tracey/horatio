import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Loading } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { withdrawnText } from "./leaveHome";

/**
 * Leaving the home troupe for none (#459), from the Home troupe card: a dialog
 * says first, by name, what ends there and what stays.
 */
export function LeaveHome({
  character,
  troupeId,
  troupeName,
  waitingFor,
}: {
  character: CharacterOut;
  troupeId: string;
  troupeName: string;
  /** The troupe a request to make home waits on, which leaving leaves alone. */
  waitingFor?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" className="max-w-full py-2" onClick={() => setOpen(true)}>
        Leave {troupeName} and have no home troupe
      </Button>
      <Dialog title={`Leave ${troupeName}?`} open={open} onClose={() => setOpen(false)}>
        <Confirm character={character} troupeId={troupeId} troupeName={troupeName} waitingFor={waitingFor} onClose={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

function Confirm({
  character,
  troupeId,
  troupeName,
  waitingFor,
  onClose,
}: {
  character: CharacterOut;
  troupeId: string;
  troupeName: string;
  waitingFor?: string;
  onClose: () => void;
}) {
  const path = { params: { path: { character_id: character.id, troupe_id: troupeId } } };
  const found = useQuery({
    queryKey: ["leaving", character.id, troupeId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/troupes/{troupe_id}/leaving", path)),
  });
  const leave = useRulesAction(() => unwrap(api.DELETE("/api/characters/{character_id}/troupes/{troupe_id}", path)));

  // Once it has left, asking again fails; what it said before still stands.
  if (!found.data) return found.error ? <ErrorText error={found.error} /> : <Loading />;
  const { titles, requests, free_changes_open } = found.data;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>
        {character.name} will have no home troupe until a troupe, {troupeName} or another, accepts it again.
      </p>
      {titles.length > 0 ? (
        <div>
          <p>Its titles in {troupeName} end:</p>
          <ul aria-label="Titles that end" className="mt-1 list-disc pl-5">
            {titles.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p>It holds no titles there.</p>
      )}
      {requests.length > 0 ? (
        <div>
          <p>Its requests waiting there are withdrawn:</p>
          <ul aria-label="Requests withdrawn" className="mt-1 list-disc pl-5">
            {requests.map((r, i) => (
              <li key={i}>{withdrawnText(r)}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p>It has no requests waiting there.</p>
      )}
      {free_changes_open && <p>Its free changes end now, and won't reopen when a troupe accepts it again.</p>}
      {waitingFor && <p>Its request to make {waitingFor} its home still waits.</p>}
      <p>Its sheet, XP and history stay as they are, and so do its visits to other troupes.</p>
      <p className="text-mist">{troupeName}'s storytellers will be told.</p>
      <ErrorText error={leave.error} />
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="danger" disabled={leave.isPending} onClick={() => leave.mutate(undefined, { onSuccess: onClose })}>
          Leave {troupeName}
        </Button>
      </div>
    </div>
  );
}
