import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError, unwrap } from "../../api/client";
import type { AnswerIn, MyDowntime, QuestionOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

type Draft = Record<string, { body: string; structured?: Record<string, unknown> }[]>;

function toDraft(downtime: MyDowntime): Draft {
  const draft: Draft = {};
  for (const q of downtime.questions) draft[q.id] = [];
  for (const a of downtime.answers) {
    const list = draft[a.question_id] ?? [];
    list[a.slot - 1] = { body: a.body, structured: a.structured };
    draft[a.question_id] = list;
  }
  for (const q of downtime.questions) {
    draft[q.id] = (draft[q.id] ?? []).filter(Boolean);
    if (q.kind === "custom" && draft[q.id]!.length === 0) draft[q.id] = [{ body: "" }];
  }
  return draft;
}

function toAnswers(draft: Draft): AnswerIn[] {
  return Object.entries(draft).flatMap(([question_id, answers]) =>
    answers.map((a, i) => ({ question_id, slot: i + 1, body: a.body, structured: a.structured ?? null })),
  );
}

export function DowntimeTab({ characterId }: { characterId: string }) {
  const path = { params: { path: { character_id: characterId } } };
  const downtime = useQuery({
    queryKey: ["downtime", characterId],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/characters/{character_id}/downtime", path));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const [draft, setDraft] = useState<Draft>({});
  useEffect(() => {
    if (downtime.data) setDraft(toDraft(downtime.data));
  }, [downtime.data]);

  const save = useAction(() => unwrap(api.PUT("/api/characters/{character_id}/downtime/answers", { ...path, body: { answers: toAnswers(draft) } })));
  const submit = useAction(async () => {
    await unwrap(api.PUT("/api/characters/{character_id}/downtime/answers", { ...path, body: { answers: toAnswers(draft) } }));
    return unwrap(api.POST("/api/characters/{character_id}/downtime/submit", path));
  });

  if (downtime.isPending) return <Loading />;
  if (downtime.error) return <ErrorText error={downtime.error} />;
  const d = downtime.data;
  if (!d) return <Empty>There is no open downtime for this character. Downtimes come from its home troupe.</Empty>;

  const used = (kind: string) =>
    d.questions.filter((q) => q.action_kind === kind).reduce((n, q) => n + (draft[q.id]?.length ?? 0), 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
      <div className="flex flex-col gap-4">
        {d.questions.map((q) => (
          <QuestionCard
            key={q.id}
            question={q}
            answers={draft[q.id] ?? []}
            remaining={q.kind === "action" ? (d.allowance[q.action_kind!] ?? 0) - used(q.action_kind!) : 0}
            onChange={(answers) => setDraft({ ...draft, [q.id]: answers })}
          />
        ))}
        <ErrorText error={save.error ?? submit.error} />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => save.mutate(undefined)} disabled={save.isPending}>
            Save draft
          </Button>
          <Button onClick={() => submit.mutate(undefined)} disabled={submit.isPending}>
            {d.status === "submitted" ? "Save and resubmit" : "Submit downtime"}
          </Button>
        </div>
      </div>
      <aside className="flex flex-col gap-4">
        <Card title={d.cycle_name}>
          <p className="text-sm">
            Due <time>{new Date(d.closes_at).toLocaleString()}</time>
          </p>
          <p className="text-xs text-mist">Accepted until {new Date(d.grace_ends_at).toLocaleString()}</p>
          {d.completion_xp_awarded != null ? (
            <p className="mt-2 text-sm text-gold">You earned {d.completion_xp_awarded} XP for completing it.</p>
          ) : (
            d.completion_xp > 0 && <p className="mt-2 text-sm">Submitting it earns {d.completion_xp} XP.</p>
          )}
          <div className="mt-3">
            {d.status === "submitted" ? <Badge tone="gold">submitted{d.late ? " (late)" : ""}</Badge> : <Badge>draft</Badge>}
          </div>
        </Card>
        <Card title="Your actions">
          <ul className="text-sm">
            {Object.entries(d.allowance)
              .filter(([, n]) => n > 0)
              .map(([kind, n]) => (
                <li key={kind} className="flex justify-between">
                  <span className="capitalize">{kind.replace(/_/g, " ")}</span>
                  <span>
                    {used(kind)} / {n}
                  </span>
                </li>
              ))}
          </ul>
          <ul className="mt-3 border-t border-ash pt-2 text-xs text-mist">
            {d.breakdown.map((b, i) => (
              <li key={i}>
                +{b.amount} {b.action_kind.replace(/_/g, " ")} from {b.source}
              </li>
            ))}
            {d.adjustments.map((a, i) => (
              <li key={`adj${i}`}>
                {a.delta > 0 ? "+" : ""}
                {a.delta} {a.action_kind.replace(/_/g, " ")}: {a.reason}
              </li>
            ))}
          </ul>
        </Card>
        {submit.isSuccess && <Notice>Submitted. You can keep editing until the grace period ends.</Notice>}
      </aside>
    </div>
  );
}

function QuestionCard({
  question,
  answers,
  remaining,
  onChange,
}: {
  question: QuestionOut;
  answers: Draft[string];
  remaining: number;
  onChange: (answers: Draft[string]) => void;
}) {
  const canAdd =
    question.kind === "action" && remaining > 0 && (question.max_answers == null || answers.length < question.max_answers);
  const set = (i: number, value: Draft[string][number]) => onChange(answers.map((a, j) => (j === i ? value : a)));

  return (
    <Card
      title={
        <>
          {question.prompt}
          {question.required && <span className="ml-1 text-blood-bright">*</span>}
        </>
      }
    >
      {question.help_text && <p className="mb-3 text-sm text-mist">{question.help_text}</p>}
      <div className="flex flex-col gap-3">
        {answers.map((a, i) => (
          <div key={i} className="flex flex-col gap-2">
            <AnswerInput question={question} value={a.body} onChange={(body) => set(i, { ...a, body })} />
            {question.action_kind?.startsWith("influence") && (
              <Field label="Action level">
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={String(a.structured?.level ?? "")}
                  onChange={(e) => set(i, { ...a, structured: { ...a.structured, level: Number(e.target.value) } })}
                />
              </Field>
            )}
            {question.kind === "action" && (
              <Button variant="ghost" className="self-start px-0" onClick={() => onChange(answers.filter((_, j) => j !== i))}>
                Remove this action
              </Button>
            )}
          </div>
        ))}
        {canAdd && (
          <Button variant="secondary" className="self-start" onClick={() => onChange([...answers, { body: "" }])}>
            Add an action ({remaining} left)
          </Button>
        )}
        {question.kind === "action" && answers.length === 0 && !canAdd && <Empty>No actions of this kind left.</Empty>}
      </div>
    </Card>
  );
}

function AnswerInput({ question, value, onChange }: { question: QuestionOut; value: string; onChange: (v: string) => void }) {
  switch (question.answer_type) {
    case "choice":
      return (
        <Select value={value} onChange={(e) => onChange(e.target.value)} aria-label={question.prompt}>
          <option value="">Choose…</option>
          {question.options?.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </Select>
      );
    case "yes_no":
      return (
        <Select value={value} onChange={(e) => onChange(e.target.value)} aria-label={question.prompt}>
          <option value="">Choose…</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </Select>
      );
    case "number":
      return <Input type="number" value={value} onChange={(e) => onChange(e.target.value)} aria-label={question.prompt} />;
    case "short_text":
      return <Input value={value} onChange={(e) => onChange(e.target.value)} aria-label={question.prompt} />;
    default:
      return <Textarea value={value} onChange={(e) => onChange(e.target.value)} aria-label={question.prompt} />;
  }
}
