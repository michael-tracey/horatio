import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** The troupe's NPCs, each with a way into its Play View, badges to print for
 * them, and the fast way to make another. */
export function NpcsTab({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const path = { params: { path: { troupe_id: troupeId } } };
  const npcs = useQuery({ queryKey: ["npcs", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/npcs", path)) });
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const create = useAction(async (wizard: boolean) => {
    const npc = await unwrap(api.POST("/api/troupes/{troupe_id}/npcs", { ...path, body: { name, splat: "vampire", wizard } }));
    navigate(`/characters/${npc.id}${wizard ? "/create" : ""}`);
  });
  const all = npcs.data ?? [];
  const ticked = all.filter((n) => selected.has(n.id));
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (!next.delete(id)) next.add(id);
    setSelected(next);
  };
  // The same badge sheets as the Characters tab's, opened in a new tab so what is ticked stays.
  const badges = (ids: string[]) => window.open(`/print/troupes/${troupeId}/badges?characters=${ids.join(",")}`, "_blank", "noopener");

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <Card title="NPCs">
        {all.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-mist">Game badges:</span>
            <Button variant="secondary" disabled={!ticked.length} onClick={() => badges(ticked.map((n) => n.id))}>
              Badges for selected ({ticked.length})
            </Button>
            <Button variant="secondary" onClick={() => badges(all.map((n) => n.id))}>
              Badges for all NPCs
            </Button>
          </div>
        )}
        {npcs.isPending ? (
          <Loading />
        ) : all.length ? (
          <ul className="divide-y divide-ash">
            {all.map((n) => (
              <li key={n.id} className="flex items-center gap-3 py-2">
                <input type="checkbox" aria-label={`Select ${n.name}`} checked={selected.has(n.id)} onChange={() => toggle(n.id)} />
                <Link to={`/characters/${n.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:text-gold">
                  <Avatar name={n.name} picture={n.picture} clan={n.clan} />
                  <span className="truncate">{n.name}</span>
                </Link>
                <span className="text-sm text-mist capitalize">{n.splat}</span>
                <Link
                  to={`/play/characters/${n.id}`}
                  aria-label={`Play ${n.name}`}
                  className="inline-flex min-h-9 items-center rounded-md bg-blood px-3 text-sm font-medium text-parchment hover:bg-blood-bright"
                >
                  Play
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No NPCs yet.</Empty>
        )}
        <ErrorText error={npcs.error} />
      </Card>
      <Card title="New NPC">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(false);
          }}
        >
          <Field label="Name">
            <Input required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <ErrorText error={create.error} />
          <Button type="submit" disabled={!name || create.isPending}>
            Quick build
          </Button>
          <Button type="button" variant="secondary" disabled={!name || create.isPending} onClick={() => create.mutate(true)}>
            Use the creation wizard
          </Button>
          <p className="text-xs text-mist">Quick build sets ratings directly, with a running tally of what the NPC is worth.</p>
        </form>
      </Card>
    </div>
  );
}
