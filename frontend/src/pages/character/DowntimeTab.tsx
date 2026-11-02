import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError, unwrap } from "../../api/client";
import type { AnswerIn, FeedingIn, InfluenceStandingOut, MyDowntime, QuestChoiceOut, QuestionOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { feedingActionsSpent } from "../../feeding";
import { useAction } from "../../hooks";
import { chosenAction, offered, reachable, reachNote } from "../../influence";
import { DISCOVERY_BLOCK, LOOKUP_LEVEL, LOOKUP_NOTE } from "../../influenceLookups";
import { questChoiceText } from "../quests/quests";
import { BlockTarget } from "./BlockTarget";
import { useLeaveWarning } from "./CartPanel";
import { type Answers, EMPTY_FORM, type Form, formReducer, toAnswers, unsaved } from "./downtimeForm";
import { FeedingCard } from "./FeedingCard";

/** Action questions and the Quest action each spend an action of their kind. */
const spends = (q: QuestionOut) => q.kind === "action" || q.kind === "quest";

/** "+3", "−2": an allowance line or adjustment, with a true minus. */
function signed(n: number): string {
  return n < 0 ? `\u2212${-n}` : `+${n}`;
}

/** How long typing has to stop for before the answers are saved. */
const AUTOSAVE_MS = 2000;

/** The answers as sent to the server, and the edit they go up to. */
type Sent = { version: number; answers: AnswerIn[]; feeding: FeedingIn | null };

/** An action just removed, to put back with Undo. */
type Removed = { question: string; index: number; answer: Answers[number] };

export function DowntimeTab({ characterId }: { characterId: string }) {
  const path = { params: { path: { character_id: characterId } } };
  const key = ["downtime", characterId];
  const client = useQueryClient();
  const downtime = useQuery({
    queryKey: key,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/characters/{character_id}/downtime", path));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const [form, change] = useReducer(formReducer, EMPTY_FORM);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [removed, setRemoved] = useState<Removed | null>(null);
  const dates = useDates();
  // Whatever the server sends is merged in, never over a part edited since the last save.
  useEffect(() => {
    if (downtime.data) change({ type: "loaded", downtime: downtime.data });
  }, [downtime.data]);

  // Saving waits on its own answer, not a refetch of the page. Saves go one at a time.
  const save = useMutation({
    scope: { id: `downtime-${characterId}` },
    mutationFn: ({ answers, feeding }: Sent) => unwrap(api.PUT("/api/characters/{character_id}/downtime/answers", { ...path, body: { answers, feeding } })),
    onSuccess: (saved, sent) => {
      change({ type: "saved", version: sent.version });
      client.setQueryData(key, saved);
      setSavedAt(new Date());
    },
  });
  const submit = useAction(async (sent: Sent) => {
    await unwrap(api.PUT("/api/characters/{character_id}/downtime/answers", { ...path, body: { answers: sent.answers, feeding: sent.feeding } }));
    change({ type: "saved", version: sent.version });
    setSavedAt(new Date());
    const submitted = await unwrap(api.POST("/api/characters/{character_id}/downtime/submit", path));
    client.setQueryData(key, submitted);
    return submitted;
  });

  const dirty = unsaved(form);
  const failed = save.isError && save.variables?.version === form.version;
  const saving = save.isPending || submit.isPending;
  // The Feeding section goes with the answers once it has been loaded.
  const sent = (f: Form, d: MyDowntime): Sent => ({ version: f.version, answers: toAnswers(f.draft), feeding: d.feeding && f.feeding ? f.feeding : null });
  // For the timer and for leaving, which run after the render they were set up in.
  const latest = useRef({ form, data: downtime.data, busy: submit.isPending, inFlight: undefined as number | undefined, mutate: save.mutate });
  useEffect(() => {
    latest.current = { form, data: downtime.data, busy: submit.isPending, inFlight: save.isPending ? save.variables?.version : undefined, mutate: save.mutate };
  });
  const saveNow = (always = false) => {
    const { form, data, busy, inFlight, mutate } = latest.current;
    if (!data || busy || inFlight === form.version || (!always && !unsaved(form))) return;
    mutate(sent(form, data));
  };

  // Autosave once typing stops. A save that failed isn't tried again until the next edit.
  useEffect(() => {
    if (!dirty || failed || saving) return;
    const timer = setTimeout(saveNow, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [form.version, dirty, failed, saving]);
  // Save at once when the player switches away (a phone's other app) or leaves the tab.
  useEffect(() => {
    const away = () => document.visibilityState === "hidden" && saveNow();
    document.addEventListener("visibilitychange", away);
    return () => {
      document.removeEventListener("visibilitychange", away);
      saveNow();
    };
  }, []);
  useLeaveWarning(dirty || saving);

  if (downtime.isPending) return <Loading />;
  if (downtime.error) return <ErrorText error={downtime.error} />;
  const d = downtime.data;
  if (!d) return <Empty>There is no open downtime for this character. Downtimes come from its home troupe.</Empty>;

  const { draft, feeding } = form;
  // Feeding actions and patrols come out of the general actions.
  const fed = d.feeding && feeding ? feedingActionsSpent(feeding, d.feeding.rack ?? false, (d.feeding.territories ?? []).length > 0) : 0;
  const used = (kind: string) =>
    d.questions.filter((q) => q.action_kind === kind).reduce((n, q) => n + (draft[q.id]?.length ?? 0), 0) + (kind === "general" ? fed : 0);
  const setAnswers = (question: string, answers: Answers) => change({ type: "answers", question, answers });
  const remove = (question: string, index: number) => {
    const answers = draft[question] ?? [];
    setRemoved({ question, index, answer: answers[index]! });
    setAnswers(question, answers.filter((_, j) => j !== index));
  };
  const undo = () => {
    if (!removed) return;
    const answers = [...(draft[removed.question] ?? [])];
    answers.splice(removed.index, 0, removed.answer);
    setAnswers(removed.question, answers);
    setRemoved(null);
  };

  const status = saving ? (
    "Saving…"
  ) : failed ? (
    <span className="text-blood-bright">
      Couldn't save:{" "}
      <button type="button" className="underline hover:text-parchment" onClick={() => saveNow(true)}>
        try again
      </button>
    </span>
  ) : dirty ? (
    "Not saved yet"
  ) : submit.isSuccess ? (
    "Submitted. You can keep editing until the grace period ends."
  ) : (
    savedAt && `Saved ${dates.time(savedAt)}`
  );

  // The troupe's absentee downtimes ask for a game attended lately (issue #438).
  if (d.closed)
    return (
      <Card title={d.cycle_name}>
        <p className="text-sm">{d.closed}</p>
      </Card>
    );

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
      <div className="flex flex-col gap-4">
        {d.feeding && feeding && (
          <FeedingCard
            feeding={d.feeding}
            value={feeding}
            onChange={(value) => change({ type: "feeding", feeding: value })}
            actionsLeft={(d.allowance.general ?? 0) - used("general")}
            characterId={characterId}
            onDowntime={(saved) => client.setQueryData(key, saved)}
          />
        )}
        {d.questions.map((q) => {
          const remaining = spends(q) ? (d.allowance[q.action_kind!] ?? 0) - used(q.action_kind!) : 0;
          const answers = draft[q.id] ?? [];
          // Undo puts it back while there is room for it.
          const canUndo = removed?.question === q.id && remaining > 0 && (q.max_answers == null || answers.length < q.max_answers);
          return (
            <QuestionCard
              key={q.id}
              characterId={characterId}
              question={q}
              answers={answers}
              remaining={remaining}
              influence={q.kind === "action" ? d.influence?.find((s) => s.action_kind === q.action_kind) : undefined}
              quests={d.quests ?? []}
              onChange={(next) => setAnswers(q.id, next)}
              onRemove={(i) => remove(q.id, i)}
              onUndo={canUndo ? undo : undefined}
            />
          );
        })}
        <ErrorText error={save.error ?? submit.error} />
        {/* On a phone, the buttons and what became of them stay at the foot of the screen. */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 max-lg:sticky max-lg:bottom-0 max-lg:z-10 max-lg:-mx-4 max-lg:border-t max-lg:border-ash max-lg:bg-night/95 max-lg:px-4 max-lg:py-3 max-lg:backdrop-blur">
          <Button variant="secondary" onClick={() => saveNow(true)} disabled={saving}>
            Save draft
          </Button>
          <Button onClick={() => submit.mutate(sent(form, d))} disabled={saving}>
            {d.status === "submitted" ? "Save and resubmit" : "Submit downtime"}
          </Button>
          <p role="status" aria-live="polite" className="text-sm text-mist">
            {status}
          </p>
        </div>
      </div>
      {/* On a phone, the deadline and status come first, before the questions. */}
      <aside className="contents lg:flex lg:flex-col lg:gap-4">
        <Card title={d.cycle_name} className="order-first lg:order-none">
          <p className="text-sm">
            Due <time dateTime={d.closes_at}>{dates.deadline(d.closes_at)}</time>
          </p>
          <p className="text-xs text-mist">Accepted until {dates.deadline(d.grace_ends_at)}</p>
          {d.completion_xp_awarded != null ? (
            <p className="mt-2 text-sm text-gold">You earned {d.completion_xp_awarded} XP for completing it.</p>
          ) : (
            d.completion_xp > 0 && <p className="mt-2 text-sm">Submitting it earns {d.completion_xp} XP.</p>
          )}
          <div className="mt-3">
            {d.status === "submitted" ? <Badge tone="gold">Submitted{d.late ? " (late)" : ""}</Badge> : <Badge>Draft</Badge>}
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
                {signed(b.amount)} {b.action_kind.replace(/_/g, " ")} {Math.abs(b.amount) === 1 ? "action" : "actions"}{" "}
                {b.source === "Everyone" ? "(everyone gets these)" : `from ${b.source}`}
                {b.note && <span className="block pl-3">{b.note}</span>}
              </li>
            ))}
            {d.adjustments.map((a, i) => (
              <li key={`adj${i}`}>
                {signed(a.delta)} {a.action_kind.replace(/_/g, " ")}: {a.reason}
              </li>
            ))}
          </ul>
          {Object.entries(d.short ?? {}).map(([kind, n]) => (
            <p key={kind} className="mt-2 text-xs text-blood-bright">
              {n} {kind.replace(/_/g, " ")} {n === 1 ? "action" : "actions"} short of what is owed this month.
            </p>
          ))}
        </Card>
      </aside>
    </div>
  );
}

function QuestionCard({
  characterId,
  question,
  answers,
  remaining,
  influence,
  quests,
  onChange,
  onRemove,
  onUndo,
}: {
  characterId: string;
  question: QuestionOut;
  answers: Answers;
  remaining: number;
  influence?: InfluenceStandingOut;
  quests: QuestChoiceOut[];
  onChange: (answers: Answers) => void;
  onRemove: (index: number) => void;
  /** Puts back the action just removed from this question. */
  onUndo?: () => void;
}) {
  const noQuests = question.kind === "quest" && quests.length === 0;
  const canAdd = spends(question) && !noQuests && remaining > 0 && (question.max_answers == null || answers.length < question.max_answers);
  const set = (i: number, value: Answers[number]) => onChange(answers.map((a, j) => (j === i ? value : a)));

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
            {question.kind === "quest" && <QuestChoice quests={quests} fields={a.structured} onChange={(structured) => set(i, { ...a, structured })} />}
            <AnswerInput question={question} value={a.body} onChange={(body) => set(i, { ...a, body })} />
            {influence && influence.actions.length > 0 && (
              <InfluenceFields characterId={characterId} standing={influence} fields={a.structured} onChange={(structured) => set(i, { ...a, structured })} />
            )}
            {spends(question) && (
              <Button variant="ghost" className="self-start px-0" onClick={() => onRemove(i)}>
                Remove this action
              </Button>
            )}
          </div>
        ))}
        {onUndo && (
          <p className="flex items-center gap-2 text-sm text-mist">
            Action removed.
            <Button variant="secondary" onClick={onUndo}>
              Undo
            </Button>
          </p>
        )}
        {canAdd && (
          <Button variant="secondary" className="self-start" onClick={() => onChange([...answers, { body: "" }])}>
            Add an action ({remaining} left)
          </Button>
        )}
        {noQuests && answers.length === 0 && <Empty>No quests to choose. Quests shared with this character, or posted to the troupe, show here.</Empty>}
        {spends(question) && !noQuests && answers.length === 0 && !canAdd && <Empty>No actions of this kind left.</Empty>}
      </div>
    </Card>
  );
}

/** The quest a Quest action is for: one the character leads or is in, or can join by choosing it. */
function QuestChoice({
  quests,
  fields,
  onChange,
}: {
  quests: QuestChoiceOut[];
  fields: Record<string, unknown> | undefined;
  onChange: (fields: Record<string, unknown> | undefined) => void;
}) {
  const chosen = typeof fields?.quest_id === "string" ? fields.quest_id : "";
  return (
    <Field label="Which quest">
      <Select
        value={chosen}
        onChange={(e) => {
          const id = e.target.value;
          // The scenario it was for goes with the quest it was for.
          onChange(id === chosen ? fields : id ? { quest_id: id } : undefined);
        }}
      >
        <option value="">Choose…</option>
        {quests.map((q) => (
          <option key={q.id} value={q.id}>
            {questChoiceText(q)}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/** An influence answer's specialisation and named action, offering only the actions the character can reach. */
function InfluenceFields({
  characterId,
  standing,
  fields,
  onChange,
}: {
  characterId: string;
  standing: InfluenceStandingOut;
  fields: Record<string, unknown> | undefined;
  onChange: (fields: Record<string, unknown>) => void;
}) {
  const specialization = typeof fields?.specialization === "string" ? fields.specialization : "";
  const action = chosenAction(standing.actions, fields);
  const others = standing.options.filter((o) => !standing.held.includes(o));
  const choose = (next: { specialization?: string; action?: string }) => {
    const spec = next.specialization ?? specialization;
    const key = next.action ?? action?.key ?? "";
    const kept = standing.actions.find((a) => a.key === key);
    // An action from before they had names keeps its level until it changes.
    const { level: _old, ...rest } = fields ?? {};
    // What a discovery block hides goes with it.
    if (key !== DISCOVERY_BLOCK) {
      delete rest.block;
      delete rest.block_entry;
    }
    onChange({ ...rest, specialization: spec || undefined, action: kept && reachable(standing, kept, spec) ? key : undefined });
  };
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <Field label="Specialisation">
        <Select value={specialization} onChange={(e) => choose({ specialization: e.target.value })}>
          <option value="">None</option>
          {standing.held.length > 0 && (
            <optgroup label="Yours">
              {standing.held.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </optgroup>
          )}
          <optgroup label={standing.held.length ? "Others" : "All"}>
            {others.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </optgroup>
        </Select>
      </Field>
      <Field
        label="Action"
        hint={[reachNote(standing, specialization, action), action?.level === LOOKUP_LEVEL && !action.conflict && LOOKUP_NOTE].filter(Boolean).join(" ") || null}
      >
        <Select value={action?.key ?? ""} onChange={(e) => choose({ action: e.target.value })}>
          <option value="">Choose…</option>
          {[...offered(standing, specialization), ...(action && !reachable(standing, action, specialization) ? [action] : [])].map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </Select>
      </Field>
      {action?.key === DISCOVERY_BLOCK && <BlockTarget characterId={characterId} fields={fields} onChange={onChange} />}
    </div>
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
