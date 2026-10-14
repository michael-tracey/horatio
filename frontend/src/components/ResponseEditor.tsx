import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { WorkItemOut } from "../api/types";
import { useAction } from "../hooks";
import { Badge, Button, ErrorText, Select, Textarea } from "./ui";

/** One downtime action and the box to answer it in, with fill tables to roll from. */
export function ResponseEditor({ item, troupeId, extra }: { item: WorkItemOut; troupeId: string; extra?: React.ReactNode }) {
  const [body, setBody] = useState(item.body);
  const [table, setTable] = useState("");
  const tables = useQuery({
    queryKey: ["tables", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/random-tables", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const save = useAction(() => unwrap(api.PUT("/api/responses/{response_id}", { params: { path: { response_id: item.id } }, body: { body } })));
  const roll = useAction(async (name: string) => {
    const rolled = await unwrap(
      api.POST("/api/troupes/{troupe_id}/random-tables/{name}/roll", { params: { path: { troupe_id: troupeId, name } } }),
    );
    setBody((b) => (b ? `${b}\n${rolled.text}` : rolled.text));
  });
  const level = item.structured?.level;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-ash bg-night/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          <strong className="text-gold">{item.character_name}</strong> · {item.question}
          {level != null && <span className="text-mist"> · level {String(level)}</span>}
        </span>
        <Badge tone={item.status === "written" ? "gold" : "mist"}>{item.status}</Badge>
      </div>
      <p className="text-sm whitespace-pre-line">{item.answer}</p>
      <Textarea aria-label={`Response to ${item.character_name}`} value={body} onChange={(e) => setBody(e.target.value)} placeholder="The result…" />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => save.mutate(undefined)} disabled={save.isPending || body === item.body}>
          Save response
        </Button>
        {!!tables.data?.length && (
          <>
            <Select aria-label="Fill table" className="w-auto" value={table} onChange={(e) => setTable(e.target.value)}>
              <option value="">Fill table…</option>
              {tables.data.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
            <Button variant="secondary" disabled={!table} onClick={() => roll.mutate(table)}>
              Roll
            </Button>
          </>
        )}
        {extra}
      </div>
      <ErrorText error={save.error ?? roll.error} />
    </div>
  );
}
