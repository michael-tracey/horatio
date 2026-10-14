import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** The troupe's characters, drafts first, for its storytellers and assistants. */
export function RosterTab({ troupeId }: { troupeId: string }) {
  const roster = useQuery({
    queryKey: ["roster", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", { params: { path: { troupe_id: troupeId } } })),
  });
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;
  if (!roster.data.length) return <Empty>No characters have joined this troupe yet.</Empty>;
  return (
    <Card title="Characters">
      <ul className="divide-y divide-ash">
        {roster.data.map((entry) => (
          <RosterRow key={entry.character_id} troupeId={troupeId} entry={entry} />
        ))}
      </ul>
    </Card>
  );
}

function RosterRow({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const back = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/characters/{character_id}/return-to-draft", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { reason },
      }),
    ),
  );
  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <Link to={`/characters/${entry.character_id}?troupe=${troupeId}`} className="hover:text-gold">
            {entry.character_name}
          </Link>
          <span className="text-sm text-mist">{entry.player_name}</span>
          <Badge tone={entry.standing === "approved" ? "gold" : "blood"}>{entry.standing}</Badge>
          {entry.home && <Badge>home</Badge>}
          {entry.waiting && <Badge>waiting for you</Badge>}
        </span>
        {entry.standing === "approved" && (
          <Button variant="ghost" onClick={() => setOpen(!open)}>
            Send back to draft
          </Button>
        )}
      </div>
      {entry.note && <p className="text-xs text-blood-bright">Sent back to draft: {entry.note}</p>}
      {open && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            back.mutate(undefined);
          }}
        >
          <Input aria-label={`Reason for sending ${entry.character_name} back to draft`} required placeholder="Reason, shown to the player" value={reason} onChange={(e) => setReason(e.target.value)} className="flex-1" />
          <Button type="submit" variant="danger" disabled={!reason || back.isPending}>
            Send back
          </Button>
        </form>
      )}
      <ErrorText error={back.error} />
    </li>
  );
}
