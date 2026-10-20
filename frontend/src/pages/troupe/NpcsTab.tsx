import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** The troupe's NPCs, and the fast way to make another. */
export function NpcsTab({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const path = { params: { path: { troupe_id: troupeId } } };
  const npcs = useQuery({ queryKey: ["npcs", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/npcs", path)) });
  const [name, setName] = useState("");
  const create = useAction(async (wizard: boolean) => {
    const npc = await unwrap(api.POST("/api/troupes/{troupe_id}/npcs", { ...path, body: { name, splat: "vampire", wizard } }));
    navigate(`/characters/${npc.id}${wizard ? "/create" : ""}`);
  });

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <Card title="NPCs">
        {npcs.isPending ? (
          <Loading />
        ) : npcs.data?.length ? (
          <ul className="divide-y divide-ash">
            {npcs.data.map((n) => (
              <li key={n.id}>
                <Link to={`/characters/${n.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-gold">
                  <span className="flex items-center gap-3">
                    <Avatar name={n.name} picture={n.picture} clan={n.clan} />
                    {n.name}
                  </span>
                  <span className="text-sm text-mist capitalize">{n.splat}</span>
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
