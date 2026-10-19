import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CycleOut, ParticipantOut, QuestionIn, WorkItemOut } from "../../api/types";
import { ResponseEditor } from "../../components/ResponseEditor";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, PageTitle, Select, Tabs, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { DeliveryTab } from "./DeliveryTab";

export function CyclePage() {
  const { cycleId = "" } = useParams();
  const cycle = useQuery({
    queryKey: ["cycle", cycleId],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}", { params: { path: { cycle_id: cycleId } } })),
  });
  if (cycle.isPending) return <Loading />;
  if (cycle.error) return <ErrorText error={cycle.error} />;
  const c = cycle.data;
  const base = `/cycles/${c.id}`;
  return (
    <>
      <PageTitle
        subtitle={
          <Link to={`/troupes/${c.troupe_id}/downtimes`} className="hover:underline">
            ← All cycles
          </Link>
        }
        actions={<Badge tone={c.status === "open" ? "gold" : "mist"}>{c.status}</Badge>}
      >
        {c.name}
      </PageTitle>
      <Tabs
        tabs={[
          { to: base, label: "Overview", end: true },
          { to: `${base}/form`, label: "Form" },
          { to: `${base}/participants`, label: "Participants" },
          { to: `${base}/responses`, label: "Responses" },
          ...(c.status === "closed" || c.status === "complete" ? [{ to: `${base}/delivery`, label: "Delivery" }] : []),
        ]}
      />
      <Routes>
        <Route index element={<Overview cycle={c} />} />
        <Route path="form" element={<FormEditor cycle={c} />} />
        <Route path="participants" element={<Participants cycle={c} />} />
        <Route path="responses" element={<Responses cycle={c} />} />
        <Route path="delivery" element={<DeliveryTab cycleId={c.id} troupeId={c.troupe_id} />} />
      </Routes>
    </>
  );
}

function Overview({ cycle }: { cycle: CycleOut }) {
  const path = { params: { path: { cycle_id: cycle.id } } };
  const progress = useQuery({
    queryKey: ["progress", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/progress", path)),
    enabled: cycle.status !== "draft",
  });
  const [delivered, setDelivered] = useState<{ delivered: number; queued: number } | null>(null);
  const open = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/open", path)));
  const close = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/close", path)));
  const deliver = useAction(async () => setDelivered(await unwrap(api.POST("/api/cycles/{cycle_id}/deliver", path))));
  const complete = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/complete", path)));
  const p = progress.data;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Where it stands">
        <dl className="grid grid-cols-2 gap-y-1 text-sm">
          <dt className="text-mist">Due</dt>
          <dd>{new Date(cycle.closes_at).toLocaleString()}</dd>
          <dt className="text-mist">Accepted until</dt>
          <dd>{new Date(cycle.grace_ends_at).toLocaleString()}</dd>
          <dt className="text-mist">XP for completing</dt>
          <dd>
            <CompletionXp cycle={cycle} />
          </dd>
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {cycle.status === "draft" && (
            <Button onClick={() => open.mutate(undefined)}>Open for submissions</Button>
          )}
          {cycle.status === "open" && (
            <Button variant="secondary" onClick={() => close.mutate(undefined)}>
              Close submissions
            </Button>
          )}
          {cycle.status === "closed" && (
            <>
              <Button onClick={() => deliver.mutate(undefined)}>Deliver results</Button>
              <Button variant="secondary" onClick={() => complete.mutate(undefined)}>
                Mark complete
              </Button>
            </>
          )}
        </div>
        {cycle.status === "draft" && (
          <p className="mt-3 text-xs text-mist">Opening fixes who takes part and how many actions each character has.</p>
        )}
        {delivered !== null && (
          <Notice>
            Delivered {delivered.delivered} downtime{delivered.delivered === 1 ? "" : "s"}.
            {delivered.queued > 0 && (
              <>
                {" "}
                {delivered.queued} {delivered.queued === 1 ? "copy is" : "copies are"} on the way through the troupe's connectors;{" "}
                <Link to="delivery" className="underline">
                  see Delivery
                </Link>
                .
              </>
            )}
          </Notice>
        )}
        <ErrorText error={open.error ?? close.error ?? deliver.error ?? complete.error} />
      </Card>
      {p && (
        <Card title="Progress">
          <p className="text-sm">
            {p.submitted} of {p.participants} submitted · {p.written} of {p.responses} responses written
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded bg-ash">
            <div className="h-full bg-gold" style={{ width: `${p.responses ? (100 * p.written) / p.responses : 0}%` }} />
          </div>
          <h3 className="mt-4 mb-1 font-sans text-xs text-mist uppercase">By who</h3>
          <ProgressRows rows={p.by_assignee} />
          <h3 className="mt-4 mb-1 font-sans text-xs text-mist uppercase">By kind</h3>
          <ProgressRows rows={p.by_action_kind} />
        </Card>
      )}
    </div>
  );
}

/** What submitting earns each character; changeable until the cycle closes. */
function CompletionXp({ cycle }: { cycle: CycleOut }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(cycle.completion_xp);
  const save = useAction(async () => {
    await unwrap(api.PATCH("/api/cycles/{cycle_id}", { params: { path: { cycle_id: cycle.id } }, body: { completion_xp: amount } }));
    setEditing(false);
  });
  const changeable = cycle.status === "draft" || cycle.status === "open";
  if (!editing) {
    return (
      <span className="inline-flex items-center gap-2">
        {cycle.completion_xp}
        {changeable && (
          <button
            type="button"
            className="text-xs text-mist underline hover:text-parchment"
            onClick={() => {
              setAmount(cycle.completion_xp);
              setEditing(true);
            }}
          >
            Change
          </button>
        )}
      </span>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Input aria-label="XP for completing" type="number" min={0} max={100} required value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="h-8 w-20 py-0" />
      <Button type="submit" className="min-h-8 px-2" disabled={save.isPending}>
        Save
      </Button>
      <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => setEditing(false)}>
        Cancel
      </Button>
      {cycle.status === "open" && <span className="w-full text-xs text-mist">Characters who have already submitted keep what they got.</span>}
      <ErrorText error={save.error} />
    </form>
  );
}

function ProgressRows({ rows }: { rows: Record<string, { written?: number; total?: number }> }) {
  return (
    <ul className="text-sm">
      {Object.entries(rows).map(([name, r]) => (
        <li key={name} className="flex justify-between">
          <span className="capitalize">{name.replace(/_/g, " ")}</span>
          <span>
            {r.written ?? 0} / {r.total ?? 0}
          </span>
        </li>
      ))}
    </ul>
  );
}

const ANSWER_TYPES = [
  ["long_text", "Long text"],
  ["short_text", "Short text"],
  ["choice", "Choice"],
  ["number", "Number"],
  ["yes_no", "Yes / no"],
] as const;

function FormEditor({ cycle }: { cycle: CycleOut }) {
  const [questions, setQuestions] = useState<QuestionIn[]>(cycle.questions);
  const save = useAction(() =>
    unwrap(api.PUT("/api/cycles/{cycle_id}/questions", { params: { path: { cycle_id: cycle.id } }, body: questions })),
  );
  const editable = cycle.status === "draft" || cycle.status === "open";
  const update = (i: number, change: Partial<QuestionIn>) => setQuestions(questions.map((q, j) => (j === i ? { ...q, ...change } : q)));
  const move = (i: number, by: number) => {
    const next = [...questions];
    const [q] = next.splice(i, 1);
    next.splice(i + by, 0, q!);
    setQuestions(next);
  };

  return (
    <div className="flex flex-col gap-4">
      {cycle.status === "open" && <Notice>The cycle is open: players see changes straight away.</Notice>}
      {questions.map((q, i) => (
        <Card
          key={q.id ?? `new${i}`}
          title={q.kind === "action" ? `Action: ${q.action_kind?.replace(/_/g, " ")}` : "Custom question"}
          actions={
            editable && (
              <span className="flex gap-1">
                <Button variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">
                  ↑
                </Button>
                <Button variant="ghost" disabled={i === questions.length - 1} onClick={() => move(i, 1)} aria-label="Move down">
                  ↓
                </Button>
                <Button variant="ghost" onClick={() => setQuestions(questions.filter((_, j) => j !== i))}>
                  Remove
                </Button>
              </span>
            )
          }
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Prompt">
              <Input disabled={!editable} value={q.prompt} onChange={(e) => update(i, { prompt: e.target.value })} />
            </Field>
            <Field label="Answer type">
              <Select disabled={!editable} value={q.answer_type} onChange={(e) => update(i, { answer_type: e.target.value as QuestionIn["answer_type"] })}>
                {ANSWER_TYPES.map(([v, label]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Help text">
              <Textarea rows={2} disabled={!editable} value={q.help_text ?? ""} onChange={(e) => update(i, { help_text: e.target.value })} />
            </Field>
            {q.answer_type === "choice" && (
              <Field label="Options, one per line">
                <Textarea rows={2} disabled={!editable} value={(q.options ?? []).join("\n")} onChange={(e) => update(i, { options: e.target.value.split("\n") })} />
              </Field>
            )}
            {q.kind === "action" ? (
              <Field label="Most answers" hint="Blank: as many as the character's actions allow.">
                <Input
                  type="number"
                  min={1}
                  disabled={!editable}
                  value={q.max_answers ?? ""}
                  onChange={(e) => update(i, { max_answers: e.target.value ? Number(e.target.value) : null })}
                />
              </Field>
            ) : (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" disabled={!editable} checked={!!q.required} onChange={(e) => update(i, { required: e.target.checked })} />
                Must be answered
              </label>
            )}
          </div>
        </Card>
      ))}
      {editable && (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setQuestions([...questions, { kind: "custom", prompt: "New question", answer_type: "long_text", help_text: "", options: [], required: false }])}>
            Add a custom question
          </Button>
          <Button onClick={() => save.mutate(undefined)} disabled={save.isPending}>
            Save form
          </Button>
        </div>
      )}
      <ErrorText error={save.error} />
      {save.isSuccess && <Notice>Saved.</Notice>}
    </div>
  );
}

function Participants({ cycle }: { cycle: CycleOut }) {
  const participants = useQuery({
    queryKey: ["participants", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/participants", { params: { path: { cycle_id: cycle.id } } })),
  });
  if (cycle.status === "draft") return <Empty>Participants are fixed when the cycle opens.</Empty>;
  if (participants.isPending) return <Loading />;
  if (participants.error) return <ErrorText error={participants.error} />;
  return (
    <div className="flex flex-col gap-4">
      {participants.data.length === 0 && <Empty>No participants.</Empty>}
      {participants.data.map((p) => (
        <ParticipantCard key={p.id} cycle={cycle} participant={p} />
      ))}
    </div>
  );
}

function ParticipantCard({ cycle, participant }: { cycle: CycleOut; participant: ParticipantOut }) {
  const path = { params: { path: { cycle_id: cycle.id, participant_id: participant.id } } };
  const [adjust, setAdjust] = useState({ action_kind: "general", delta: 1, reason: "" });
  const remove = useAction(() => unwrap(api.DELETE("/api/cycles/{cycle_id}/participants/{participant_id}", path)));
  const late = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/participants/{participant_id}/accept-late", path)));
  const add = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/participants/{participant_id}/adjustments", { ...path, body: adjust })));

  return (
    <Card
      title={
        <Link to={`/characters/${participant.character_id}`} className="hover:underline">
          {participant.character_name}
        </Link>
      }
      actions={
        <span className="flex gap-2">
          {participant.removed ? (
            <Badge tone="blood">removed</Badge>
          ) : (
            <Badge tone={participant.submission_status === "submitted" ? "gold" : "mist"}>
              {participant.submission_status ?? "not started"}
              {participant.submitted_late ? " (late)" : ""}
            </Badge>
          )}
          {participant.completion_xp_awarded != null && <Badge tone="gold">+{participant.completion_xp_awarded} XP</Badge>}
        </span>
      }
    >
      <p className="text-sm">
        {Object.entries(participant.allowance)
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`)
          .join(" · ") || "No actions"}
      </p>
      {participant.adjustments.map((a, i) => (
        <p key={i} className="text-xs text-mist">
          {a.delta > 0 ? "+" : ""}
          {a.delta} {a.action_kind}: {a.reason}
        </p>
      ))}
      {!participant.removed && cycle.status === "open" && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-mist">Adjust, accept late, or remove</summary>
          <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_5rem_2fr_auto]">
            <Select aria-label="Action kind" value={adjust.action_kind} onChange={(e) => setAdjust({ ...adjust, action_kind: e.target.value })}>
              {Object.keys(participant.allowance).map((k) => (
                <option key={k} value={k}>
                  {k.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
            <Input aria-label="Change" type="number" value={adjust.delta} onChange={(e) => setAdjust({ ...adjust, delta: Number(e.target.value) })} />
            <Input aria-label="Reason" placeholder="Reason" value={adjust.reason} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />
            <Button variant="secondary" disabled={!adjust.reason} onClick={() => add.mutate(undefined)}>
              Adjust
            </Button>
          </div>
          <div className="mt-3 flex gap-2">
            {!participant.late_accepted && (
              <Button variant="secondary" onClick={() => late.mutate(undefined)}>
                Accept late
              </Button>
            )}
            <Button variant="danger" onClick={() => remove.mutate(undefined)}>
              Remove from cycle
            </Button>
          </div>
        </details>
      )}
      <ErrorText error={remove.error ?? late.error ?? add.error} />
    </Card>
  );
}

function Responses({ cycle }: { cycle: CycleOut }) {
  const [filter, setFilter] = useState<"all" | "unassigned" | "assigned" | "written">("all");
  const items = useQuery({
    queryKey: ["responses", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/responses", { params: { path: { cycle_id: cycle.id } } })),
  });
  const staff = useQuery({
    queryKey: ["staff", cycle.troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", { params: { path: { troupe_id: cycle.troupe_id } } })),
  });
  if (items.isPending) return <Loading />;
  if (items.error) return <ErrorText error={items.error} />;
  const shown = items.data.filter((i) => filter === "all" || i.status === filter);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {(["all", "unassigned", "assigned", "written"] as const).map((f) => (
          <Button key={f} variant={f === filter ? "secondary" : "ghost"} className="capitalize" onClick={() => setFilter(f)}>
            {f} ({f === "all" ? items.data.length : items.data.filter((i) => i.status === f).length})
          </Button>
        ))}
      </div>
      {shown.length === 0 && <Empty>Nothing here.</Empty>}
      {shown.map((item) => (
        <ResponseEditor key={item.id} item={item} troupeId={cycle.troupe_id} extra={<AssignSelect item={item} staff={staff.data ?? []} />} />
      ))}
    </div>
  );
}

function AssignSelect({ item, staff }: { item: WorkItemOut; staff: { user_id: string; display_name: string }[] }) {
  const assign = useAction((value: string) =>
    unwrap(
      api.PUT("/api/responses/{response_id}/assignment", {
        params: { path: { response_id: item.id } },
        body: value === "any" ? { any_narrator: true } : { any_narrator: false, user_id: value || null },
      }),
    ),
  );
  const value = item.assigned_to_any_narrator ? "any" : (item.assigned_to_user_id ?? "");
  return (
    <>
      <Select aria-label="Assign to" className="w-auto" value={value} onChange={(e) => assign.mutate(e.target.value)}>
        <option value="">Unassigned</option>
        <option value="any">Any narrator</option>
        {staff.map((s) => (
          <option key={s.user_id} value={s.user_id}>
            {s.display_name}
          </option>
        ))}
      </Select>
      {assign.error && <ErrorText error={assign.error} />}
    </>
  );
}
