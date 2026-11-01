import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import type { QuestActionOut, WorkItemOut } from "../api/types";
import { useAction } from "../hooks";
import { DISCOVERY_BLOCK, LOOKUP_LEVEL } from "../influenceLookups";
import { questType } from "../pages/quests/quests";
import { STATUS_NAMES } from "../pages/troupe/responsesList";
import { CombinedAnswers, DiscoveryBlock, LookupFill, type Combined } from "./InfluenceLookupTools";
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
  // Follow the response when it is saved from elsewhere, such as a lookup combined with it.
  useEffect(() => setBody(item.body), [item.body]);
  // The character's other answers to a lookup, filled in with this one.
  const [others, setOthers] = useState<Combined[]>([]);
  const [table, setTable] = useState("");
  const tables = useQuery({
    queryKey: ["tables", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/random-tables", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/responses/{response_id}", { params: { path: { response_id: item.id } }, body: { body } }));
    for (const o of others) await unwrap(api.PUT("/api/responses/{response_id}", { params: { path: { response_id: o.id } }, body: { body: o.text } }));
    setOthers([]);
  });
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
        <Badge tone={item.status === "written" ? "gold" : "mist"}>{STATUS_NAMES[item.status as keyof typeof STATUS_NAMES] ?? item.status}</Badge>
      </div>
      <p className="text-sm whitespace-pre-line">{item.answer}</p>
      {item.quest && <QuestAction item={item} quest={item.quest} troupeId={troupeId} link={canLog} />}
      {item.influence_blocks.length > 0 && (
        <p className="text-sm text-gold" role="note">
          May be up against {item.influence_blocks.map((b) => b.text).join("; ")}. The cost is yours to judge.
        </p>
      )}
      <Textarea aria-label={`Response to ${item.character_name}`} value={body} onChange={(e) => setBody(e.target.value)} placeholder="The result…" />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => save.mutate(undefined)} disabled={save.isPending || (body === item.body && !others.length)}>
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
        {canLog && influence?.level === LOOKUP_LEVEL && (
          <LookupFill
            item={item}
            onFill={(own, rest) => {
              setBody(own);
              setOthers(rest);
            }}
          />
        )}
        {extra}
      </div>
      <ErrorText error={save.error ?? roll.error} />
      <CombinedAnswers others={others} onChange={setOthers} />
      {canLog && influence?.action_key === DISCOVERY_BLOCK && <DiscoveryBlock item={item} onWrite={setBody} />}
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

/** A Quest action's quest beside it: its scenario, its requirements and who else acted; and recording the scenario's
 * result, which answers every member's Quest action on it. */
function QuestAction({ item, quest: q, troupeId, link }: { item: WorkItemOut; quest: QuestActionOut; troupeId: string; link: boolean }) {
  const [result, setResult] = useState<"passed" | "failed">("passed");
  const [text, setText] = useState(q.success_text);
  const [ends, setEnds] = useState(false);
  const record = useAction(() =>
    unwrap(api.POST("/api/responses/{response_id}/quest-result", { params: { path: { response_id: item.id } }, body: { result, text, ends: result === "failed" && ends } })),
  );
  const met = q.requirements.filter((r) => r.met);
  const toMeet = q.requirements.filter((r) => !r.met);
  const open = q.status === "active" && q.scenario != null && !q.recorded_here && q.result !== "passed";
  return (
    <section aria-label={`Quest: ${q.name}`} className="flex flex-col gap-1 rounded-md border border-ash p-3 text-sm">
      <p>
        {link ? (
          <Link to={`/troupes/${troupeId}/quests/${q.id}`} className="text-gold hover:text-parchment">
            {q.name}
          </Link>
        ) : (
          <span className="text-gold">{q.name}</span>
        )}{" "}
        <span className="text-mist">
          · {questType(q)}
          {q.scenario != null && ` · Scenario ${q.scenario} of ${q.scenario_count}`}
        </span>
      </p>
      {met.length > 0 && <p className="text-mist">Met: {met.map((r) => (r.met_by_name ? `${r.label} (${r.met_by_name})` : r.label)).join("; ")}</p>}
      {toMeet.length > 0 && <p className="text-mist">Still to meet: {toMeet.map((r) => r.label).join("; ")}</p>}
      <p className="text-mist">{q.acted.length ? `Also put in a Quest action: ${q.acted.join(", ")}.` : "No one else put in a Quest action for it."}</p>
      {q.not_spent.length > 0 && (
        <p className="text-blood-bright" role="note">
          Not spent the action this scenario needs: {q.not_spent.join(", ")}. Nothing's Simple, Vol. II Issue 1, p. 102.
        </p>
      )}
      {q.result && (
        <p className="text-gold">
          Scenario {q.scenario}: {q.result}
          {q.recorded_here ? (q.awaiting_delivery ? ", recorded here; it goes out with this cycle's delivery." : ", recorded here, and delivered.") : ", recorded at a game."}
        </p>
      )}
      {q.status !== "active" && <p className="text-mist">The quest is {q.status}.</p>}
      {open && (
        <form
          aria-label={`Result of scenario ${q.scenario}`}
          className="mt-2 flex flex-col gap-2 border-t border-ash pt-2"
          onSubmit={(e) => {
            e.preventDefault();
            record.mutate(undefined);
          }}
        >
          <Field label="Result">
            <Select
              className="w-auto"
              value={result}
              onChange={(e) => {
                const value = e.target.value as "passed" | "failed";
                setResult(value);
                setText(value === "passed" ? q.success_text : q.fail_text);
              }}
            >
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
            </Select>
          </Field>
          <Field label="What the party is told" hint="It answers every Quest action on this scenario, and goes out with the cycle's delivery.">
            <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          {result === "failed" && (
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={ends} onChange={(e) => setEnds(e.target.checked)} />
              The quest fails (otherwise they try the scenario again)
            </label>
          )}
          <div>
            <Button type="submit" disabled={record.isPending}>
              Record scenario {q.scenario}'s result
            </Button>
          </div>
          <ErrorText error={record.error} />
        </form>
      )}
    </section>
  );
}
