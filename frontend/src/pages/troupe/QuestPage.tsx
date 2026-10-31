import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { QuestCharacterChoice, QuestOut, QuestRequirementOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, RichText, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { guidanceText, meetsNow, offerText, questStatus, questType, resultText, type Option } from "../quests/quests";
import { RequirementBuilder } from "../quests/RequirementBuilder";
import { QuestFields, type QuestDraft } from "./QuestsTab";

/** One quest, for staff: build it, check and meet its requirements, send it, and see it through. */
export function QuestPage({ troupeId }: { troupeId: string }) {
  const { questId = "" } = useParams();
  const quest = useQuery({
    queryKey: ["quest", questId],
    queryFn: () => unwrap(api.GET("/api/quests/{quest_id}", { params: { path: { quest_id: questId } } })),
  });
  const characters = useQuery({
    queryKey: ["quest-characters", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-characters", { params: { path: { troupe_id: troupeId } } })),
  });
  if (quest.isPending) return <Loading />;
  if (quest.error) return <ErrorText error={quest.error} />;
  const q = quest.data;
  const everyone = characters.data ?? [];
  return (
    <div className="flex flex-col gap-4">
      <Overview quest={q} troupeId={troupeId} />
      <Requirements quest={q} everyone={everyone} />
      <Scenarios quest={q} everyone={everyone} />
      <Party quest={q} everyone={everyone} />
      {(q.status === "completed" || q.status === "failed") && <Tale quest={q} />}
      {q.deliveries.length > 0 && <Deliveries quest={q} />}
      <Log quest={q} />
    </div>
  );
}

function Overview({ quest: q, troupeId }: { quest: QuestOut; troupeId: string }) {
  const [editing, setEditing] = useState<QuestDraft | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const path = { params: { path: { quest_id: q.id } } };
  const staff = useQuery({
    queryKey: ["staff", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", { params: { path: { troupe_id: troupeId } } })),
    enabled: q.can_assign,
  });
  const save = useAction(async (draft: QuestDraft) => {
    await unwrap(api.PUT("/api/quests/{quest_id}", { ...path, body: draft }));
    setEditing(null);
  });
  const assign = useAction((value: string) =>
    unwrap(api.PUT("/api/quests/{quest_id}/assignment", { ...path, body: value === "any" ? { any_narrator: true } : { any_narrator: false, user_id: value || null } })),
  );
  const accept = useAction(() => unwrap(api.POST("/api/quests/{quest_id}/accept", path)));
  const read = useAction(() => unwrap(api.POST("/api/quests/{quest_id}/read", path)));
  const send = useAction(() => unwrap(api.POST("/api/quests/{quest_id}/send", path)));
  const close = useAction(async (note: string) => {
    await unwrap(api.POST("/api/quests/{quest_id}/close", { ...path, body: { note } }));
    setClosing(null);
  });
  const draftOf = (): QuestDraft => ({
    name: q.name,
    objective: q.objective,
    category: q.category,
    difficulty: q.difficulty,
    downtime_only: q.downtime_only,
    staff_notes: q.staff_notes,
    leader_id: q.leader?.id ?? null,
    offer: q.offer,
    unlock_quest_id: q.unlock_quest_id,
    unlock_scenario: q.unlock_scenario,
  });
  const open = q.status === "draft" || q.status === "active";

  return (
    <Card
      title={q.name}
      actions={
        <span className="flex flex-wrap items-center gap-2">
          <Badge tone={q.status === "active" ? "gold" : q.status === "closed" || q.status === "failed" ? "blood" : "mist"}>{questStatus(q.status)}</Badge>
          {q.can_edit && !editing && (
            <Button variant="ghost" className="min-h-8 px-2" onClick={() => setEditing(draftOf())}>
              Edit
            </Button>
          )}
        </span>
      }
    >
      {editing ? (
        <form
          aria-label="Edit quest"
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(editing);
          }}
        >
          <QuestFields troupeId={troupeId} draft={editing} onChange={(change) => setEditing({ ...editing, ...change })} most={q.location ? 10 : 5} />
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-mist">
            {questType(q)} · {q.leader ? `Leader: ${q.leader.name}` : "No leader yet"} · {offerText(q.offer)}
            {q.offer === "unlocked" && q.unlock_quest_name && ` (scenario ${q.unlock_scenario} of ${q.unlock_quest_name})`}
          </p>
          {q.objective && <p className="whitespace-pre-line">{q.objective}</p>}
          {q.location && (
            <p>
              When it is completed,{" "}
              <Link to={`/troupes/${troupeId}/locations/${q.location.id}`} className="text-gold hover:text-parchment">
                {q.location.name}
              </Link>{" "}
              changes: {q.location.change}.
            </p>
          )}
          <p className="text-mist">{guidanceText(q.guidance)}</p>
          {q.staff_notes && <p className="whitespace-pre-line text-mist">Staff notes: {q.staff_notes}</p>}
          {q.request && (
            <p className="text-mist">
              Asked for by {q.request.character_name} ({q.request.player_name}): “{q.request.objective}”
              {q.request.reason && ` Why: ${q.request.reason}`}
              {q.request.companions && ` Would bring: ${q.request.companions}`}
            </p>
          )}
          {q.status === "closed" && <p>Closed: {q.close_note}</p>}
          {q.ended_on && (
            <p>
              {questStatus(q.status)} on {q.ended_on}, by {q.finished_by.join(", ") || "no one"}.
            </p>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        {q.can_assign && (
          <Select aria-label="Assign the quest to" className="w-auto" value={q.assigned_to_any_narrator ? "any" : (q.assigned_to_user_id ?? "")} onChange={(e) => assign.mutate(e.target.value)}>
            <option value="">Unassigned</option>
            <option value="any">Any narrator</option>
            {staff.data?.map((s) => (
              <option key={s.user_id} value={s.user_id}>
                {s.display_name}
              </option>
            ))}
          </Select>
        )}
        {!q.can_assign && (
          <span className="text-mist">{q.assigned_to_any_narrator ? "Assigned to any narrator" : q.assigned_to_name ? `Assigned to ${q.assigned_to_name}` : "Not assigned"}</span>
        )}
        {q.assigned_to_any_narrator && !q.can_assign && (
          <Button variant="secondary" onClick={() => accept.mutate(undefined)}>
            Accept
          </Button>
        )}
        <Button variant="ghost" onClick={() => read.mutate(undefined)}>
          Mark read
        </Button>
        {q.read_by.length > 0 && <span className="text-mist">Read by {q.read_by.join(", ")}</span>}
      </div>
      {q.can_send && open && (
        <div className="mt-3 flex flex-wrap gap-2">
          {q.status === "draft" && <Button onClick={() => send.mutate(undefined)}>Send requirements</Button>}
          {closing === null && (
            <Button variant="danger" onClick={() => setClosing("")}>
              Close quest
            </Button>
          )}
        </div>
      )}
      {closing !== null && (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            close.mutate(closing);
          }}
        >
          <Field label="Why it is closed">
            <Input required value={closing} onChange={(e) => setClosing(e.target.value)} placeholder="No longer relevant" />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" disabled={close.isPending}>
              Close it
            </Button>
            <Button type="button" variant="ghost" onClick={() => setClosing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      <ErrorText error={assign.error ?? accept.error ?? read.error ?? send.error ?? close.error} />
    </Card>
  );
}

function Requirements({ quest: q, everyone }: { quest: QuestOut; everyone: QuestCharacterChoice[] }) {
  const add = useAction((options: Option[]) =>
    unwrap(api.POST("/api/quests/{quest_id}/requirements", { params: { path: { quest_id: q.id } }, body: { options } })),
  );
  const open = q.status === "draft" || q.status === "active";
  return (
    <Card title="Requirements">
      {q.requirements.length === 0 ? (
        <Empty>No requirements yet.</Empty>
      ) : (
        <ol className="mb-4 flex flex-col gap-3">
          {q.requirements.map((r, i) => (
            <RequirementRow key={r.id} quest={q} requirement={r} number={i + 1} everyone={everyone} />
          ))}
        </ol>
      )}
      {q.can_edit && open && <RequirementBuilder onAdd={(options) => add.mutateAsync(options)} pending={add.isPending} error={add.error} />}
    </Card>
  );
}

function RequirementRow({ quest: q, requirement: r, number, everyone }: { quest: QuestOut; requirement: QuestRequirementOut; number: number; everyone: QuestCharacterChoice[] }) {
  const path = { params: { path: { quest_id: q.id, requirement_id: r.id } } };
  const party = r.checks.map((c) => c.character_id);
  const [who, setWho] = useState(party[0] ?? "");
  const [option, setOption] = useState(0);
  const met = useAction(() => unwrap(api.POST("/api/quests/{quest_id}/requirements/{requirement_id}/met", { ...path, body: { character_id: who, option } })));
  const unmet = useAction(() => unwrap(api.DELETE("/api/quests/{quest_id}/requirements/{requirement_id}/met", path)));
  const remove = useAction(() => unwrap(api.DELETE("/api/quests/{quest_id}/requirements/{requirement_id}", path)));
  const open = q.status === "draft" || q.status === "active";
  const others = everyone.filter((c) => !party.includes(c.id));

  return (
    <li aria-label={`Requirement ${number}`} className="rounded-md border border-ash p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-parchment">{r.label}</span>
        {r.met ? (
          <Badge tone="gold">Met</Badge>
        ) : (
          q.can_edit &&
          open && (
            <Button variant="ghost" className="min-h-8 px-2" onClick={() => remove.mutate(undefined)}>
              Remove
            </Button>
          )
        )}
      </div>
      {r.met ? (
        <p className="mt-1 text-mist">
          Met by {r.met_by_name}
          {r.met_patron && " as a patron"}
          {r.met_label && r.options.length > 1 && `: ${r.met_label}`}
          {r.spent && ` (${r.spent})`}.{" "}
          {q.can_check && open && (
            <Button variant="ghost" className="min-h-8 px-2" onClick={() => unmet.mutate(undefined)}>
              Unmark
            </Button>
          )}
        </p>
      ) : (
        q.can_check && (
          <>
            <ul className="mt-1 text-mist">
              {r.options.map((o, i) => {
                const meets = meetsNow(r.checks, i);
                const unknown = r.checks.length > 0 && r.checks.every((c) => c.meets[i] === null);
                return (
                  <li key={i}>
                    {o.label}: {unknown ? "staff judge it" : meets.length ? `${meets.join(", ")} meet${meets.length === 1 ? "s" : ""} it now` : "no one in the party meets it now"}
                  </li>
                );
              })}
            </ul>
            {open && (
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <Field label="Met by">
                  <Select value={who} onChange={(e) => setWho(e.target.value)} className="w-auto">
                    <option value="">Choose a character</option>
                    <optgroup label="The party">
                      {r.checks.map((c) => (
                        <option key={c.character_id} value={c.character_id}>
                          {c.name}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="A patron">
                      {others.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </optgroup>
                  </Select>
                </Field>
                {r.options.length > 1 && (
                  <Field label="With">
                    <Select value={option} onChange={(e) => setOption(Number(e.target.value))} className="w-auto">
                      {r.options.map((o, i) => (
                        <option key={i} value={i}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                )}
                <Button variant="secondary" disabled={!who || met.isPending} onClick={() => met.mutate(undefined)}>
                  Mark met
                </Button>
              </div>
            )}
          </>
        )
      )}
      <ErrorText error={met.error ?? unmet.error ?? remove.error} />
    </li>
  );
}

function Scenarios({ quest: q, everyone }: { quest: QuestOut; everyone: QuestCharacterChoice[] }) {
  const [editing, setEditing] = useState<{ success_text: string; fail_text: string }[] | null>(null);
  const save = useAction(async (scenarios: { success_text: string; fail_text: string }[]) => {
    await unwrap(
      api.PUT("/api/quests/{quest_id}", {
        params: { path: { quest_id: q.id } },
        body: {
          name: q.name,
          objective: q.objective,
          category: q.category,
          difficulty: q.difficulty,
          downtime_only: q.downtime_only,
          staff_notes: q.staff_notes,
          leader_id: q.leader?.id ?? null,
          offer: q.offer,
          unlock_quest_id: q.unlock_quest_id,
          unlock_scenario: q.unlock_scenario,
          scenarios,
        },
      }),
    );
    setEditing(null);
  });
  const next = q.scenarios.find((s) => s.result !== "passed");
  return (
    <Card
      title="Scenarios"
      actions={
        q.can_edit &&
        !editing && (
          <Button variant="ghost" className="min-h-8 px-2" onClick={() => setEditing(q.scenarios.map((s) => ({ success_text: s.success_text, fail_text: s.fail_text })))}>
            Edit scenarios
          </Button>
        )
      }
    >
      {editing ? (
        <form
          aria-label="Edit scenarios"
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(editing);
          }}
        >
          {editing.map((s, i) => (
            <fieldset key={i} aria-label={`Scenario ${i + 1}`} className="grid gap-2 rounded-md border border-ash p-3 sm:grid-cols-2">
              <legend className="px-1 text-xs text-mist">Scenario {i + 1}</legend>
              <Field label="Success text">
                <Textarea rows={3} value={s.success_text} onChange={(e) => setEditing(editing.map((t, j) => (j === i ? { ...t, success_text: e.target.value } : t)))} />
              </Field>
              <Field label="Fail text">
                <Textarea rows={3} value={s.fail_text} onChange={(e) => setEditing(editing.map((t, j) => (j === i ? { ...t, fail_text: e.target.value } : t)))} />
              </Field>
            </fieldset>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => setEditing([...editing, { success_text: "", fail_text: "" }])}>
              Add a scenario
            </Button>
            {editing.length > 1 && (
              <Button type="button" variant="ghost" onClick={() => setEditing(editing.slice(0, -1))}>
                Remove the last
              </Button>
            )}
            <Button type="submit" disabled={save.isPending}>
              Save scenarios
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      ) : (
        <>
          {q.downtime && (
            <p aria-label="Quest actions" className="mb-3 text-sm text-mist">
              In {q.downtime.cycle_name}: {q.downtime.acted.length ? `Quest actions from ${q.downtime.acted.join(", ")}.` : "no Quest actions yet."}
              {q.downtime.not_spent.length > 0 && (
                <span className="block text-blood-bright">
                  Not spent the action the next scenario needs: {q.downtime.not_spent.join(", ")}. Nothing's Simple, Vol. II Issue 1, p. 102.
                </span>
              )}
            </p>
          )}
          <ol className="flex flex-col gap-3">
            {q.scenarios.map((s) => (
              <li key={s.number} aria-label={`Scenario ${s.number}`} className="rounded-md border border-ash p-3 text-sm">
                <p className="mb-1 text-gold">{s.result ? resultText(s) : `Scenario ${s.number}`}</p>
                {s.result ? (
                  <RichText text={s.result_text} />
                ) : (
                  <>
                    <p className="text-mist">Success: {s.success_text || "not written yet"}</p>
                    <p className="text-mist">Fail: {s.fail_text || "not written yet"}</p>
                  </>
                )}
                {s.awaiting_delivery && <p className="mt-1 text-xs text-mist">Recorded in {s.cycle_name}; it goes out with that cycle's delivery.</p>}
                {s.resources.map((r, i) => (
                  <p key={i} className="mt-1 text-xs text-gold">
                    {r.name} expended Resources {r.dots}: {r.successes} {r.successes === 1 ? "success" : "successes"}.
                  </p>
                ))}
                {q.location && q.can_send && q.status === "active" && next?.number === s.number && (
                  <ExpendResources quest={q} number={s.number} everyone={everyone} />
                )}
                {q.can_send &&
                  q.status === "active" &&
                  next?.number === s.number &&
                  (q.downtime_only ? (
                    <p className="mt-2 text-xs text-mist">Downtime only: its result is recorded from a Quest action, in a downtime cycle's responses.</p>
                  ) : (
                    <SendResult quest={q} number={s.number} success={s.success_text} fail={s.fail_text} />
                  ))}
              </li>
            ))}
          </ol>
        </>
      )}
    </Card>
  );
}

/** The Resources shortcut on a location quest (Vol. II Issue 1, p. 120). */
function ExpendResources({ quest: q, number, everyone }: { quest: QuestOut; number: number; everyone: QuestCharacterChoice[] }) {
  const [who, setWho] = useState(q.leader?.id ?? "");
  const [dots, setDots] = useState(q.difficulty);
  const expend = useAction(() =>
    unwrap(api.POST("/api/quests/{quest_id}/scenarios/{number}/resources", { params: { path: { quest_id: q.id, number } }, body: { character_id: who, dots } })),
  );
  return (
    <form
      aria-label={`Resources on scenario ${number}`}
      className="mt-3 flex flex-col gap-2 border-t border-ash pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        expend.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">Resources equal to the difficulty, {q.difficulty}, succeed this step; each dot over gives one more success.</p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Expended by">
          <Select value={who} onChange={(e) => setWho(e.target.value)} className="w-auto">
            <option value="">Choose a character</option>
            {everyone.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Resources dots">
          <Input type="number" min={1} max={10} value={dots} onChange={(e) => setDots(Number(e.target.value))} className="w-24" />
        </Field>
        <Button type="submit" variant="secondary" disabled={!who || expend.isPending}>
          Expend Resources
        </Button>
      </div>
      <ErrorText error={expend.error} />
    </form>
  );
}

function SendResult({ quest: q, number, success, fail }: { quest: QuestOut; number: number; success: string; fail: string }) {
  const [result, setResult] = useState<"passed" | "failed">("passed");
  const [text, setText] = useState(success);
  const [ends, setEnds] = useState(false);
  const send = useAction(() =>
    unwrap(api.POST("/api/quests/{quest_id}/scenarios/{number}/result", { params: { path: { quest_id: q.id, number } }, body: { result, text, ends: result === "failed" && ends } })),
  );
  return (
    <form
      aria-label={`Result of scenario ${number}`}
      className="mt-3 flex flex-col gap-2 border-t border-ash pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate(undefined);
      }}
    >
      <Field label="Result">
        <Select
          value={result}
          onChange={(e) => {
            const value = e.target.value as "passed" | "failed";
            setResult(value);
            setText(value === "passed" ? success : fail);
          }}
          className="w-auto"
        >
          <option value="passed">Passed</option>
          <option value="failed">Failed</option>
        </Select>
      </Field>
      <Field label="What the party is told">
        <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      {result === "failed" && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={ends} onChange={(e) => setEnds(e.target.checked)} />
          The quest fails (otherwise they try the scenario again)
        </label>
      )}
      <div>
        <Button type="submit" disabled={send.isPending}>
          Send scenario {number}'s result
        </Button>
      </div>
      <ErrorText error={send.error} />
    </form>
  );
}

function Party({ quest: q, everyone }: { quest: QuestOut; everyone: QuestCharacterChoice[] }) {
  const [who, setWho] = useState("");
  const path = { params: { path: { quest_id: q.id } } };
  const add = useAction(async (joined: boolean) => {
    await unwrap(api.POST("/api/quests/{quest_id}/members", { ...path, body: { character_ids: [who], joined } }));
    setWho("");
  });
  const remove = useAction((characterId: string) =>
    unwrap(api.DELETE("/api/quests/{quest_id}/members/{character_id}", { params: { path: { quest_id: q.id, character_id: characterId } } })),
  );
  const taken = new Set([q.leader?.id, ...q.members.map((m) => m.character_id)]);
  const open = q.status === "draft" || q.status === "active";
  const status = { invited: "can join", joined: "in the party", left: "left" } as Record<string, string>;
  return (
    <Card title="Party">
      <p className="mb-2 text-sm">Leader: {q.leader?.name ?? "no one yet: the first to join leads it"}</p>
      {q.members.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1 text-sm">
          {q.members.map((m) => (
            <li key={m.character_id} className="flex flex-wrap items-center gap-2">
              <span>
                {m.name} <span className="text-mist">({m.player_name})</span> · {status[m.status] ?? m.status}
              </span>
              {q.can_send && open && (
                <Button variant="ghost" className="min-h-8 px-2" aria-label={`Take ${m.name} off the quest`} onClick={() => remove.mutate(m.character_id)}>
                  Take off
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {q.can_send && open && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Character">
            <Select value={who} onChange={(e) => setWho(e.target.value)} className="w-auto">
              <option value="">Choose a character</option>
              {everyone
                .filter((c) => !taken.has(c.id))
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </Select>
          </Field>
          <Button variant="secondary" disabled={!who || add.isPending} onClick={() => add.mutate(false)}>
            Offer it to them
          </Button>
          <Button variant="secondary" disabled={!who || add.isPending} onClick={() => add.mutate(true)}>
            Add to the party
          </Button>
        </div>
      )}
      <ErrorText error={add.error ?? remove.error} />
    </Card>
  );
}

function Tale({ quest: q }: { quest: QuestOut }) {
  const [tale, setTale] = useState<string | null>(null);
  const save = useAction(async (approve: boolean) => {
    await unwrap(api.PUT("/api/quests/{quest_id}/tale", { params: { path: { quest_id: q.id } }, body: { tale: tale ?? q.tale, approve } }));
    setTale(null);
  });
  return (
    <Card title="Telling the Tale" actions={q.tale_approved ? <Badge tone="gold">Approved</Badge> : q.tale ? <Badge>Waiting for approval</Badge> : null}>
      <p className="mb-2 text-sm text-mist">The leader's player writes what happened; staff edit it and approve it as the official account (p. 102).</p>
      {q.can_check ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(true);
          }}
        >
          <Field label="The tale">
            <Textarea rows={5} value={tale ?? q.tale} onChange={(e) => setTale(e.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending}>
              Approve the tale
            </Button>
            <Button type="button" variant="secondary" disabled={save.isPending} onClick={() => save.mutate(false)}>
              Save without approving
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      ) : q.tale ? (
        <RichText text={q.tale} />
      ) : (
        <Empty>Not told yet.</Empty>
      )}
    </Card>
  );
}

function Deliveries({ quest: q }: { quest: QuestOut }) {
  const retry = useAction((id: string) => unwrap(api.POST("/api/deliveries/{delivery_id}/retry", { params: { path: { delivery_id: id } } })));
  return (
    <Card title="Sent on connectors">
      <ul className="flex flex-col gap-1 text-sm">
        {q.deliveries.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-2">
            <span>
              {d.subject} to {d.character_name} on {d.channel}: {d.status}
              {d.last_error && <span className="text-mist"> ({d.last_error})</span>}
            </span>
            {d.status === "failed" && q.can_check && (
              <Button variant="ghost" className="min-h-8 px-2" onClick={() => retry.mutate(d.id)}>
                Retry
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={retry.error} />
    </Card>
  );
}

function Log({ quest: q }: { quest: QuestOut }) {
  const dates = useDates();
  const [text, setText] = useState("");
  const add = useAction(async () => {
    await unwrap(api.POST("/api/quests/{quest_id}/log", { params: { path: { quest_id: q.id } }, body: { text } }));
    setText("");
  });
  return (
    <Card title="Log">
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined);
        }}
      >
        <Field label="Add a note to the log">
          <Input required value={text} onChange={(e) => setText(e.target.value)} className="min-w-48 flex-1" />
        </Field>
        <Button type="submit" variant="secondary" disabled={add.isPending}>
          Add
        </Button>
      </form>
      <ErrorText error={add.error} />
      <ul className="flex flex-col gap-1 text-sm">
        {q.log.map((e, i) => (
          <li key={i}>
            <time dateTime={e.at} className="text-mist">
              {dates.dateTime(e.at)}
            </time>{" "}
            {e.actor_name ?? "Horatio"} {e.text}
          </li>
        ))}
      </ul>
    </Card>
  );
}
