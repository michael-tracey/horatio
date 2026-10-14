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
          {entry.kind === "npc" ? <Badge>NPC</Badge> : <Badge tone={entry.standing === "approved" ? "gold" : "blood"}>{entry.standing}</Badge>}
          {entry.home && <Badge>home</Badge>}
          {entry.waiting && <Badge>waiting for you</Badge>}
        </span>
        {entry.kind === "pc" && entry.standing === "approved" && (
          <Button variant="ghost" onClick={() => setOpen(!open)}>
            Send back to draft
          </Button>
        )}
      </div>
      {entry.note && <p className="text-xs text-blood-bright">Sent back to draft: {entry.note}</p>}
      <TitleEditor troupeId={troupeId} entry={entry} />
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

/** The character's titles here as chips, with a picker to give another. */
function TitleEditor({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const [adding, setAdding] = useState("");
  const titles = useQuery({
    queryKey: ["titles", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const save = useAction((names: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/titles", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { titles: names },
      }),
    ),
  );
  const all = [...(titles.data?.troupe ?? []), ...(titles.data?.catalogue ?? [])].filter((t) => !entry.titles.includes(t));
  const listId = `titles-${entry.character_id}`;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {entry.titles.map((t) => (
        <span key={t} className="flex items-center gap-1">
          <Badge tone="gold">{t}</Badge>
          <button aria-label={`Take the title ${t} from ${entry.character_name}`} className="text-mist hover:text-blood-bright" onClick={() => save.mutate(entry.titles.filter((x) => x !== t))}>
            ×
          </button>
        </span>
      ))}
      <form
        className="flex gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (adding) save.mutate([...entry.titles, adding]);
          setAdding("");
        }}
      >
        <Input list={listId} aria-label={`Give ${entry.character_name} a title`} placeholder="Give a title…" value={adding} onChange={(e) => setAdding(e.target.value)} className="h-8 min-h-8 w-44 py-1 text-xs" />
        <datalist id={listId}>
          {all.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </form>
      <ErrorText error={save.error} />
    </div>
  );
}
