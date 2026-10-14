import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TableOut } from "../../api/types";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

export function TablesTab({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const tables = useQuery({ queryKey: ["tables", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/random-tables", path)) });
  if (tables.isPending) return <Loading />;
  if (tables.error) return <ErrorText error={tables.error} />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        Fill tables give random results for common actions. An entry can name another table in square brackets —
        "You hunt near [Location]." — to fill that part from it.
      </p>
      {tables.data.length === 0 && <Empty>No fill tables yet.</Empty>}
      {tables.data.map((t) => (
        <TableCard key={t.id} troupeId={troupeId} table={t} canEdit={canEdit} />
      ))}
      {canEdit && <TableCard troupeId={troupeId} canEdit />}
    </div>
  );
}

function TableCard({ troupeId, table, canEdit }: { troupeId: string; table?: TableOut; canEdit: boolean }) {
  const [name, setName] = useState(table?.name ?? "");
  const [entries, setEntries] = useState((table?.entries ?? []).join("\n"));
  const [rolled, setRolled] = useState<string | null>(null);
  const save = useAction(async () => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/random-tables", {
        params: { path: { troupe_id: troupeId } },
        body: { name, entries: entries.split("\n") },
      }),
    );
    if (!table) {
      setName("");
      setEntries("");
    }
  });
  const roll = useAction(async () => {
    const r = await unwrap(
      api.POST("/api/troupes/{troupe_id}/random-tables/{name}/roll", { params: { path: { troupe_id: troupeId, name: table!.name } } }),
    );
    setRolled(r.text);
  });

  return (
    <Card title={table ? table.name : "New fill table"} actions={table && <Button variant="secondary" onClick={() => roll.mutate(undefined)}>Roll</Button>}>
      {rolled && <p className="mb-3 rounded-md bg-night p-3 text-sm">{rolled}</p>}
      {canEdit ? (
        <div className="flex flex-col gap-3">
          {!table && (
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          )}
          <Field label="Entries, one per line">
            <Textarea rows={6} value={entries} onChange={(e) => setEntries(e.target.value)} />
          </Field>
          <Button className="self-start" onClick={() => save.mutate(undefined)} disabled={!name || save.isPending}>
            Save table
          </Button>
        </div>
      ) : (
        <p className="text-sm text-mist">{table?.entries.length} entries</p>
      )}
      <ErrorText error={save.error ?? roll.error} />
    </Card>
  );
}
