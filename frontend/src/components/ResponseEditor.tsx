import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { WorkItemOut } from "../api/types";
import { useAction } from "../hooks";
import { Badge, Button, ErrorText, Field, Input, Select, Textarea } from "./ui";

/** One downtime action and the box to answer it in, with fill tables to roll from. */
export function ResponseEditor({
  item,
  troupeId,
  extra,
  canLog = false,
}: {
  item: WorkItemOut;
  troupeId: string;
  extra?: React.ReactNode;
  /** Storytellers and assistants can log an influence answer in the troupe's influence log. */
  canLog?: boolean;
}) {
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
  const influence = item.influence;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-ash bg-night/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          <strong className="text-gold">{item.character_name}</strong> · {item.question}
          {influence && (
            <span className="text-mist">
              {" "}
              · {influence.action ?? "no action named"}
              {influence.specialization && ` (${influence.specialization})`}
            </span>
          )}
        </span>
        <Badge tone={item.status === "written" ? "gold" : "mist"}>{item.status}</Badge>
      </div>
      <p className="text-sm whitespace-pre-line">{item.answer}</p>
      {item.influence_blocks.length > 0 && (
        <p className="text-sm text-gold" role="note">
          May be up against {item.influence_blocks.map((b) => b.text).join("; ")}. The cost is yours to judge.
        </p>
      )}
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
      {canLog && item.influence && <LogAnswer item={item} />}
    </div>
  );
}

/** Log an influence answer in the troupe's influence log, with its purpose trimmed from the player's answer. */
function LogAnswer({ item }: { item: WorkItemOut }) {
  const [purpose, setPurpose] = useState<string | null>(null);
  const path = { params: { path: { response_id: item.id } } };
  const log = useAction(async (text: string) => {
    await unwrap(api.POST("/api/responses/{response_id}/influence-entry", { ...path, body: { purpose: text } }));
    setPurpose(null);
  });
  const unlog = useAction(() => unwrap(api.DELETE("/api/responses/{response_id}/influence-entry", path)));
  const logged = item.influence_entry;

  if (logged)
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm text-mist">
        <span>
          Logged as <strong className="text-gold">{logged.short_id}</strong>
          {logged.times > 1 && `, ${logged.times} times`}.
        </span>
        <Button variant="ghost" className="px-2" onClick={() => unlog.mutate(undefined)} disabled={unlog.isPending}>
          Take it off the log
        </Button>
        <ErrorText error={unlog.error} />
      </div>
    );
  if (purpose === null)
    return (
      <Button variant="secondary" className="self-start" onClick={() => setPurpose(item.answer)} disabled={!item.influence?.action_key}>
        Log it
      </Button>
    );
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        log.mutate(purpose);
      }}
    >
      <Field label="Purpose" hint="Trim it to one line. Gossip and Word on the Street show it, never who took the action.">
        <Input value={purpose} onChange={(e) => setPurpose(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" disabled={log.isPending || !purpose.trim()}>
          Log it
        </Button>
        <Button type="button" variant="ghost" onClick={() => setPurpose(null)}>
          Cancel
        </Button>
      </div>
      <ErrorText error={log.error} />
    </form>
  );
}
