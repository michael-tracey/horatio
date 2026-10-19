import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** The troupe's characters, those whose home it is first, for its storytellers and assistants. */
export function RosterTab({ troupeId }: { troupeId: string }) {
  const roster = useQuery({
    queryKey: ["roster", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", { params: { path: { troupe_id: troupeId } } })),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;
  if (!roster.data.length) return <Empty>No characters have joined this troupe yet.</Empty>;

  const shown = roster.data;
  const ticked = shown.filter((e) => selected.has(e.character_id));
  const allTicked = ticked.length === shown.length;
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (!next.delete(id)) next.add(id);
    setSelected(next);
  };
  // Opened in a new tab, so the list (and what is ticked) stays as it was.
  const print = (ids?: string[]) =>
    window.open(`/print/troupes/${troupeId}${ids ? `?characters=${ids.join(",")}` : ""}`, "_blank", "noopener");

  return (
    <Card
      title="Characters"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!ticked.length} onClick={() => print(ticked.map((e) => e.character_id))}>
            Print selected ({ticked.length})
          </Button>
          <Button variant="secondary" onClick={() => print()}>
            Print all {shown.length}
          </Button>
        </div>
      }
    >
      <label className="flex items-center gap-2 border-b border-ash pb-2 text-sm text-mist">
        <input
          type="checkbox"
          checked={allTicked}
          ref={(box) => {
            if (box) box.indeterminate = ticked.length > 0 && !allTicked;
          }}
          onChange={() => setSelected(allTicked ? new Set() : new Set(shown.map((e) => e.character_id)))}
        />
        Select all
      </label>
      <ul className="divide-y divide-ash">
        {shown.map((entry) => (
          <RosterRow
            key={entry.character_id}
            troupeId={troupeId}
            entry={entry}
            selected={selected.has(entry.character_id)}
            onSelect={() => toggle(entry.character_id)}
          />
        ))}
      </ul>
    </Card>
  );
}

function RosterRow({
  troupeId,
  entry,
  selected,
  onSelect,
}: {
  troupeId: string;
  entry: RosterEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className="flex flex-col gap-2 py-3">
      <span className="flex flex-wrap items-center gap-2">
        <input type="checkbox" aria-label={`Select ${entry.character_name}`} checked={selected} onChange={onSelect} />
        <Link to={`/characters/${entry.character_id}`} className="hover:text-gold">
          {entry.character_name}
        </Link>
        {entry.player_id ? (
          <Link to={`/players/${entry.player_id}`} className="text-sm text-mist hover:text-gold">
            {entry.player_name}
          </Link>
        ) : (
          <span className="text-sm text-mist">{entry.player_name}</span>
        )}
        {entry.kind === "npc" ? <Badge>NPC</Badge> : entry.home ? <Badge tone="gold">home</Badge> : <Badge>visiting</Badge>}
        {entry.waiting && <Badge tone="blood">asking to make this home</Badge>}
        {entry.disciplines_waiting > 0 && (
          <Badge tone="blood">
            {entry.disciplines_waiting} discipline{entry.disciplines_waiting > 1 ? "s" : ""} to approve
          </Badge>
        )}
      </span>
      <TitleEditor troupeId={troupeId} entry={entry} />
      {entry.home && entry.kind === "pc" && <AwardXp entry={entry} />}
    </li>
  );
}

/** Experience for a character whose home troupe this is: amount and reason, as the XP history shows them. */
function AwardXp({ entry }: { entry: RosterEntry }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(3);
  const [reason, setReason] = useState("");
  const award = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp", {
        params: { path: { character_id: entry.character_id } },
        body: { amount, reason },
      }),
    );
    setOpen(false);
    setReason("");
  });
  if (!open) {
    return (
      <div>
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Award XP
        </Button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        award.mutate(undefined);
      }}
    >
      <Input
        aria-label={`XP for ${entry.character_name}`}
        type="number"
        min={1}
        required
        value={amount}
        onChange={(e) => setAmount(Number(e.target.value))}
        className="w-20"
      />
      <Input
        aria-label={`Reason for ${entry.character_name}'s XP`}
        placeholder="Reason, such as a game"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="min-w-40 flex-1"
      />
      <Button type="submit" disabled={award.isPending}>
        Award
      </Button>
      <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
        Cancel
      </Button>
      <ErrorText error={award.error} />
    </form>
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
