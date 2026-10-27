import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { TroupeOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorText, Field, Loading, Textarea } from "../../components/ui";
import { useAction, useMe } from "../../hooks";

type ClosingCharacter = components["schemas"]["ClosingCharacter"];

/**
 * Archiving the troupe, for its lead storyteller and the custodian. It first shows
 * what archiving settles: the characters it is home to are left with no home
 * troupe, visits end, an open downtime cycle ends unanswered, and games under way
 * end. A reason is needed; everyone affected is told it.
 */
export function ArchiveTroupe({ troupe }: { troupe: TroupeOut }) {
  const [open, setOpen] = useState(false);
  return (
    <Card title="Archive the troupe">
      <p className="mb-3 text-sm text-mist">
        Archiving closes the troupe to everyone, its staff and players included. Its characters are let go, so their players can ask another troupe to
        accept them. Its history is kept.
      </p>
      <Button variant="danger" onClick={() => setOpen(true)}>
        Archive troupe…
      </Button>
      <Dialog title={`Archive ${troupe.name}`} open={open} onClose={() => setOpen(false)} wide>
        <Confirm troupe={troupe} onCancel={() => setOpen(false)} />
      </Dialog>
    </Card>
  );
}

function Confirm({ troupe, onCancel }: { troupe: TroupeOut; onCancel: () => void }) {
  const navigate = useNavigate();
  const me = useMe();
  const [reason, setReason] = useState("");
  const closing = useQuery({
    queryKey: ["troupe-closing", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/closing", { params: { path: { troupe_id: troupe.id } } })),
  });
  const archive = useAction(async () => {
    await unwrap(api.POST("/api/troupes/{troupe_id}/archive", { params: { path: { troupe_id: troupe.id } }, body: { reason: reason.trim() } }));
    navigate(me.data?.is_custodian ? "/custodian/archived-troupes" : "/troupes");
  });
  if (closing.isPending) return <Loading />;
  if (closing.error) return <ErrorText error={closing.error} />;
  const c = closing.data;

  return (
    <form
      className="flex flex-col gap-4 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        archive.mutate(undefined);
      }}
    >
      <p>Archiving {troupe.name} will:</p>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <Effect title="leave these characters with no home troupe" characters={c.home} none="It is home to no characters." />
        <Effect title="end these characters' visits" characters={c.visiting} none="No characters are visiting." />
        <li>{c.cycle ? `end the open downtime cycle, ${c.cycle}, without answering or delivering it` : "No downtime cycle is open."}</li>
        <Effect title="end the games under way on these characters' Play Views, keeping their logs" characters={c.games} none="No games are under way." />
      </ul>
      <p className="text-mist">
        Their players keep their sheets, XP and history, and can ask another troupe to accept them. Titles held here end; status stays.
        {c.npcs.length > 0 && ` Its NPCs (${c.npcs.map((n) => n.name).join(", ")}) stay with it.`} Its players and staff are told.
      </p>
      <Field label="Reason" hint="Everyone affected sees this, and it goes in the troupe's log.">
        <Textarea rows={2} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={archive.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="danger" disabled={archive.isPending || !reason.trim()}>
          Archive troupe
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Effect({ title, characters, none }: { title: string; characters: ClosingCharacter[]; none: string }) {
  if (!characters.length) return <li className="text-mist">{none}</li>;
  return (
    <li>
      {title}:{" "}
      {characters.map((ch, i) => (
        <span key={ch.character_id}>
          {i > 0 && ", "}
          <span className="text-parchment">{ch.name}</span>
          {ch.player_name !== "NPC" && <span className="text-mist"> ({ch.player_name})</span>}
        </span>
      ))}
    </li>
  );
}
