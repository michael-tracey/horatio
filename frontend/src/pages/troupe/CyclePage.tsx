import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CycleOut, ParticipantOut, QuestionIn } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, PageTitle, Select, Tabs, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { closeFacts, completeFacts } from "./delivery";
import { DeliveryTab } from "./DeliveryTab";
import { FeedingTab } from "./FeedingTab";
import { LogInfluenceButton } from "./LogInfluence";
import { ResponsesTab } from "./ResponsesTab";

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
          { to: `${base}/feeding`, label: "Feeding" },
          { to: `${base}/responses`, label: "Responses" },
          { to: `${base}/delivery`, label: "Delivery" },
        ]}
      />
      <Routes>
        <Route index element={<Overview cycle={c} />} />
        <Route path="form" element={<FormEditor cycle={c} />} />
        <Route path="participants" element={<Participants cycle={c} />} />
        <Route path="feeding" element={<FeedingTab cycle={c} />} />
        <Route path="responses" element={<ResponsesTab cycle={c} />} />
        <Route path="delivery" element={<DeliveryTab cycle={c} />} />
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
  // What is still to deliver, to say before marking the cycle complete.
  const deliveries = useQuery({
    queryKey: ["deliveries", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/deliveries", path)),
    enabled: cycle.status === "closed",
  });
  const [confirming, setConfirming] = useState<"close" | "complete" | null>(null);
  const open = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/open", path)));
  const [toCeiling, setToCeiling] = useState(true);
  const close = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/close", { ...path, body: { add_to_ceiling: toCeiling } })));
  const complete = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/complete", path)));
  const dates = useDates();
  const p = progress.data;
  const now = new Date();
  const facts =
    confirming === "close" && p
      ? closeFacts({
          participants: p.participants,
          submitted: p.submitted,
          due: dates.deadline(cycle.closes_at),
          lateUntil: new Date(cycle.grace_ends_at) > now ? dates.deadline(cycle.grace_ends_at) : null,
          isPast: new Date(cycle.closes_at) <= now,
        })
      : confirming === "complete" && p && deliveries.data
        ? completeFacts({
            unwritten: p.responses - p.written,
            responses: p.responses,
            undelivered: deliveries.data.participants.filter((d) => d.due).length,
          })
        : null;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Where it stands">
        <dl className="grid grid-cols-2 gap-y-1 text-sm">
          <dt className="text-mist">Due</dt>
          <dd>{dates.deadline(cycle.closes_at)}</dd>
          <dt className="text-mist">Accepted until</dt>
          <dd>{dates.deadline(cycle.grace_ends_at)}</dd>
          <dt className="text-mist">XP for completing</dt>
          <dd>
            <CompletionXp cycle={cycle} />
          </dd>
        </dl>
        {facts ? (
          <section aria-label={confirming === "close" ? "Close submissions?" : "Mark complete?"} className="mt-4 rounded-md border border-gold/60 p-3">
            <p className="font-medium">{confirming === "close" ? "Close submissions?" : "Mark complete?"}</p>
            <ul className="mt-1 text-sm">
              {facts.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                disabled={close.isPending || complete.isPending}
                onClick={() => (confirming === "close" ? close : complete).mutate(undefined, { onSuccess: () => setConfirming(null) })}
              >
                {confirming === "close" ? "Yes, close submissions" : "Yes, mark complete"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
            </div>
          </section>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            {cycle.status === "draft" && (
              <Button onClick={() => open.mutate(undefined)}>Open for submissions</Button>
            )}
            {cycle.status === "open" && (
              <>
                <Button variant="secondary" disabled={!p} onClick={() => setConfirming("close")}>
                  Close submissions
                </Button>
                {cycle.completion_xp > 0 && (
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={toCeiling} onChange={(e) => setToCeiling(e.target.checked)} />
                    Also add {cycle.completion_xp} XP to the troupe's ceiling
                  </label>
                )}
              </>
            )}
            {cycle.status === "closed" && (
              <>
                <Link to="delivery" className="inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-4 text-sm font-medium text-parchment hover:bg-blood-bright">
                  Deliver results
                </Link>
                <Button variant="secondary" disabled={!p || !deliveries.data} onClick={() => setConfirming("complete")}>
                  Mark complete
                </Button>
              </>
            )}
          </div>
        )}
        {cycle.status === "draft" && (
          <p className="mt-3 text-xs text-mist">Opening fixes who takes part and how many actions each character has.</p>
        )}
        <ErrorText error={open.error ?? close.error ?? complete.error} />
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

/** The Quest action, as a new form has it while the troupe runs quests. */
const QUEST_ACTION: QuestionIn = {
  kind: "quest",
  action_kind: "general",
  prompt: "Quest",
  help_text: "Choose a quest your character takes part in, and say what they do towards it.",
  answer_type: "long_text",
  options: [],
  required: false,
};

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
          title={q.kind === "quest" ? "Quest action" : q.kind === "action" ? `Action: ${q.action_kind?.replace(/_/g, " ")}` : "Custom question"}
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
            {q.kind === "quest" && (
              <Field label="Spends" hint="Which of the character's actions a Quest action uses.">
                <Select disabled={!editable} value={q.action_kind ?? "general"} onChange={(e) => update(i, { action_kind: e.target.value })}>
                  {Object.entries(cycle.action_kinds ?? {}).map(([key, name]) => (
                    <option key={key} value={key}>
                      {name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {q.kind === "action" || q.kind === "quest" ? (
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
          {cycle.quests_enabled && !questions.some((q) => q.kind === "quest") && (
            <Button variant="secondary" onClick={() => setQuestions([...questions, { ...QUEST_ACTION }])}>
              Add the Quest action
            </Button>
          )}
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
        <Link to={`/characters/${participant.character_id}`} className="inline-flex items-center gap-2 hover:underline">
          <Avatar name={participant.character_name} picture={participant.picture} clan={participant.clan} size="xs" />
          {participant.character_name}
        </Link>
      }
      actions={
        <span className="flex flex-wrap items-center gap-2">
          {participant.removed ? (
            <Badge tone="blood">removed</Badge>
          ) : (
            <Badge tone={participant.submission_status === "submitted" ? "gold" : "mist"}>
              {participant.submission_status ?? "not started"}
              {participant.submitted_late ? " (late)" : ""}
            </Badge>
          )}
          {participant.completion_xp_awarded != null && <Badge tone="gold">+{participant.completion_xp_awarded} XP</Badge>}
          {/* For actions the player reported outside the form. */}
          <LogInfluenceButton
            troupeId={cycle.troupe_id}
            characterId={participant.character_id}
            cycleId={cycle.id}
            label={`Log influence for ${participant.character_name}`}
          />
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
      {Object.entries(participant.shortfall).map(([k, n]) => (
        <p key={k} className="text-xs text-blood-bright">
          Short {n} {k.replace(/_/g, " ")}: more was taken off than the allowance, which stops at 0.
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
