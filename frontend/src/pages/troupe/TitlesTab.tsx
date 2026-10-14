import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** The titles this troupe gives: the rule set's, plus its own. */
export function TitlesTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const titles = useQuery({ queryKey: ["titles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", path)) });
  const [name, setName] = useState("");
  const add = useAction(async () => {
    await unwrap(api.POST("/api/troupes/{troupe_id}/titles", { ...path, body: { name } }));
    setName("");
  });
  const remove = useAction((title: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/titles/{name}", { params: { path: { troupe_id: troupeId, name: title } } })),
  );
  if (titles.isPending) return <Loading />;
  if (titles.error) return <ErrorText error={titles.error} />;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="This troupe's own titles">
        {titles.data.troupe.length ? (
          <ul className="flex flex-wrap gap-2">
            {titles.data.troupe.map((t) => (
              <li key={t} className="flex items-center gap-1">
                <Badge tone="gold">{t}</Badge>
                <button
                  aria-label={`Remove the title ${t}`}
                  className="text-mist hover:text-blood-bright"
                  onClick={() => {
                    if (window.confirm(`Remove ${t}? Anyone holding it loses it.`)) remove.mutate(t);
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>None yet.</Empty>
        )}
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined);
          }}
        >
          <Input aria-label="New title" placeholder="Keeper of the Gate" value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit" disabled={!name || add.isPending}>
            Add
          </Button>
        </form>
        <ErrorText error={add.error ?? remove.error} />
        <p className="mt-3 text-xs text-mist">Give titles to characters on the Characters tab. A title means nothing outside this troupe.</p>
      </Card>
      <Card title="From the rules">
        <p className="text-sm leading-relaxed text-mist">{titles.data.catalogue.join(" · ")}</p>
      </Card>
    </div>
  );
}
