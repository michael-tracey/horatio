import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BackstoryQuestionIn, BackstoryQuestionOut, BackstoryQuestionSetOut, BackstorySettingsOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

type Mode = BackstorySettingsOut["mode"];
type Kind = BackstoryQuestionIn["kind"];
type Condition = NonNullable<BackstoryQuestionIn["condition"]>;

const MODES: { value: Mode; label: string; meaning: string }[] = [
  { value: "free", label: "Free text only", meaning: "Players write their backstories freely. The questions aren't offered." },
  { value: "either", label: "Free text or the questions", meaning: "Each player chooses to write freely or to answer the questions below." },
  { value: "wizard", label: "The questions only", meaning: "Players answer the questions below, then can edit the backstory they build." },
];

export const KINDS: Record<Kind, string> = {
  long: "Long answer",
  short: "Short answer",
  year: "Year (YYYY)",
  choice: "Choice",
  scale: "Scale between two poles",
  heading: "Heading only",
};

const AGES = ["Neonate", "Ancilla", "Elder"] as const;
const TRAIT_CATEGORIES = { backgrounds: "background", merits: "merit", flaws: "flaw" } as const;

/** When a question is shown, in words. */
export function conditionText(condition: BackstoryQuestionOut["condition"]): string {
  if (!condition) return "Always";
  if (condition.kind === "social_age") return `${condition.ages.join(", ")} only`;
  if (condition.kind === "sect") return `${condition.sects.join(", ")} only`;
  return `With ${condition.name} (${TRAIT_CATEGORIES[condition.category]})`;
}

/**
 * House rule: how the troupe's backstories are written, whether one must be approved
 * before a character is accepted, and the troupe's own backstory questions.
 */
export function BackstorySettings({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const settings = useQuery({
    queryKey: ["backstory-settings", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/backstory-settings", path)),
  });
  const [draft, setDraft] = useState<{ mode: Mode; required: boolean } | null>(null);
  const save = useAction(async (value: { mode: Mode; required: boolean }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/backstory-settings", { ...path, body: value }));
    setDraft(null);
  });
  const template = useAction(() => unwrap(api.POST("/api/troupes/{troupe_id}/backstory-template", path)));
  const [newSet, setNewSet] = useState("");
  const addSet = useAction(async () => {
    await unwrap(api.POST("/api/troupes/{troupe_id}/backstory-sets", { ...path, body: { name: newSet } }));
    setNewSet("");
  });
  if (settings.isPending) return <Loading />;
  if (settings.error) return <ErrorText error={settings.error} />;
  const s = settings.data;
  const now = { mode: s.mode, required: s.required };
  const shown = draft ?? now;
  const mode = MODES.find((m) => m.value === now.mode)!;

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Backstories"
        actions={
          s.can_edit &&
          draft === null && (
            <Button variant="ghost" className="min-h-8 px-2" aria-label="Change backstory settings" onClick={() => setDraft(now)}>
              Change
            </Button>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">
          Each character has one backstory, in Markdown, which only its player and this troupe's storytellers and assistant storytellers read. They read it as part
          of accepting the character, and can send it back with feedback.
        </p>
        {draft === null ? (
          <div className="flex flex-col gap-1 text-sm">
            <p>
              {mode.label}: <span className="text-mist">{mode.meaning}</span>
            </p>
            <p>{now.required ? "An approved backstory is needed before a character is accepted here." : "Accepting a character doesn't need its backstory approved."}</p>
          </div>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(shown);
            }}
          >
            <fieldset className="flex flex-col gap-2 text-sm">
              <legend className="mb-1 text-mist">How backstories are written</legend>
              {MODES.map((m) => (
                <label key={m.value} className="flex min-h-10 items-start gap-2">
                  <input type="radio" name="backstory-mode" className="mt-1" checked={shown.mode === m.value} onChange={() => setDraft({ ...shown, mode: m.value })} />
                  <span>
                    {m.label}
                    <span className="block text-xs text-mist">{m.meaning}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <label className="flex min-h-10 items-center gap-2 text-sm">
              <input type="checkbox" checked={shown.required} onChange={(e) => setDraft({ ...shown, required: e.target.checked })} />
              Need an approved backstory before accepting a character
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={save.isPending}>
                Save
              </Button>
              <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
                Cancel
              </Button>
            </div>
            <ErrorText error={save.error} />
          </form>
        )}
      </Card>

      {(now.mode !== "free" || s.sets.length > 0) && (
        <Card title="Questions">
          {s.sets.length === 0 && (
            <div className="mb-4 flex flex-col gap-2">
              <Notice>
                Start from the template: a Short Form of 24 questions and a Long Form of 112, which you can then reword, reorder, make optional or archive.
              </Notice>
              {s.can_edit && (
                <div>
                  <Button onClick={() => template.mutate(undefined)} disabled={template.isPending}>
                    Load the template
                  </Button>
                </div>
              )}
              <ErrorText error={template.error} />
            </div>
          )}
          <div className="flex flex-col gap-4">
            {s.sets.map((set, i) => (
              <QuestionSet key={set.id} set={set} canEdit={s.can_edit} sects={s.sects} first={i === 0} last={i === s.sets.length - 1} />
            ))}
          </div>
          {s.can_edit && (
            <form
              className="mt-4 flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                addSet.mutate(undefined);
              }}
            >
              <Field label="New question set">
                <Input value={newSet} maxLength={200} onChange={(e) => setNewSet(e.target.value)} placeholder="Such as Short Form" className="w-64" />
              </Field>
              <Button type="submit" variant="secondary" disabled={addSet.isPending || !newSet.trim()}>
                Add the set
              </Button>
              <ErrorText error={addSet.error} />
            </form>
          )}
        </Card>
      )}
    </div>
  );
}

function QuestionSet({ set, canEdit, sects, first, last }: { set: BackstoryQuestionSetOut; canEdit: boolean; sects: string[]; first: boolean; last: boolean }) {
  const [archived, setArchived] = useState(false);
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const change = useAction((body: { name?: string; archived?: boolean; move?: "up" | "down" }) =>
    unwrap(api.PATCH("/api/backstory-sets/{set_id}", { params: { path: { set_id: set.id } }, body })),
  );
  const add = useAction(async (body: BackstoryQuestionIn) => {
    await unwrap(api.POST("/api/backstory-sets/{set_id}/questions", { params: { path: { set_id: set.id } }, body }));
    setAdding(false);
  });
  const live = set.questions.filter((q) => !q.archived);
  const gone = set.questions.length - live.length;
  const listed = archived ? set.questions : live;

  return (
    <details className="rounded-md border border-ash p-3" open={set.questions.length <= 30}>
      <summary className="cursor-pointer">
        <span className="text-gold">{set.name}</span>
        <span className="ml-2 text-xs text-mist">
          {live.length} question{live.length === 1 ? "" : "s"}
        </span>
        {set.archived && (
          <span className="ml-2">
            <Badge>archived</Badge>
          </span>
        )}
      </summary>
      {canEdit && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          {renaming === null ? (
            <Button variant="ghost" className="min-h-8 px-2" onClick={() => setRenaming(set.name)}>
              Rename
            </Button>
          ) : (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                change.mutate({ name: renaming });
                setRenaming(null);
              }}
            >
              <Input aria-label={`New name for ${set.name}`} value={renaming} maxLength={200} onChange={(e) => setRenaming(e.target.value)} className="w-56" />
              <Button type="submit" variant="secondary" className="min-h-8 px-2" disabled={!renaming.trim()}>
                Save
              </Button>
            </form>
          )}
          <Button variant="ghost" className="min-h-8 px-2" disabled={first} onClick={() => change.mutate({ move: "up" })} aria-label={`Move ${set.name} up`}>
            ↑
          </Button>
          <Button variant="ghost" className="min-h-8 px-2" disabled={last} onClick={() => change.mutate({ move: "down" })} aria-label={`Move ${set.name} down`}>
            ↓
          </Button>
          <Button variant="ghost" className="min-h-8 px-2" onClick={() => change.mutate({ archived: !set.archived })}>
            {set.archived ? "Bring back" : "Archive the set"}
          </Button>
        </div>
      )}
      <ErrorText error={change.error} />
      <ol className="mt-3 flex flex-col divide-y divide-ash" aria-label={`${set.name} questions`}>
        {listed.map((q) => (
          <QuestionRow key={q.id} question={q} canEdit={canEdit} sects={sects} first={q.id === listed[0]?.id} last={q.id === listed[listed.length - 1]?.id} />
        ))}
      </ol>
      {gone > 0 && (
        <button type="button" className="mt-2 text-xs text-mist underline" onClick={() => setArchived(!archived)}>
          {archived ? "Hide archived questions" : `Show ${gone} archived`}
        </button>
      )}
      {canEdit &&
        (adding ? (
          <div className="mt-3">
            <QuestionForm sects={sects} onSave={(body) => add.mutate(body)} onCancel={() => setAdding(false)} saving={add.isPending} error={add.error} />
          </div>
        ) : (
          <Button variant="secondary" className="mt-3" onClick={() => setAdding(true)}>
            Add a question
          </Button>
        ))}
    </details>
  );
}

function QuestionRow({ question: q, canEdit, sects, first, last }: { question: BackstoryQuestionOut; canEdit: boolean; sects: string[]; first: boolean; last: boolean }) {
  const [editing, setEditing] = useState(false);
  const change = useAction(async (body: { question?: BackstoryQuestionIn; archived?: boolean; move?: "up" | "down" }) => {
    await unwrap(api.PATCH("/api/backstory-questions/{question_id}", { params: { path: { question_id: q.id } }, body }));
    setEditing(false);
  });
  const name = q.title || q.text;

  if (editing)
    return (
      <li className="py-3">
        <QuestionForm sects={sects} start={q} onSave={(body) => change.mutate({ question: body })} onCancel={() => setEditing(false)} saving={change.isPending} error={change.error} />
      </li>
    );
  return (
    <li className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-start sm:gap-4">
      <div className="min-w-0 flex-1 text-sm">
        <p className={q.kind === "heading" ? "text-gold" : q.archived ? "text-mist line-through" : "text-parchment"}>{q.text}</p>
        <p className="mt-1 flex flex-wrap gap-1.5 text-xs text-mist">
          <Badge>{KINDS[q.kind]}</Badge>
          {q.title && <Badge>Heading: {q.title}</Badge>}
          {q.optional && <Badge>optional</Badge>}
          {q.condition && <Badge tone="gold">{conditionText(q.condition)}</Badge>}
          {q.options.length > 0 && <span>{q.options.join(" / ")}</span>}
          {q.archived && <Badge tone="blood">archived</Badge>}
        </p>
      </div>
      {canEdit && (
        <div className="flex shrink-0 flex-wrap gap-1">
          <Button variant="ghost" className="min-h-8 px-2" onClick={() => setEditing(true)} aria-label={`Edit “${name}”`}>
            Edit
          </Button>
          <Button variant="ghost" className="min-h-8 px-2" disabled={first} onClick={() => change.mutate({ move: "up" })} aria-label={`Move “${name}” up`}>
            ↑
          </Button>
          <Button variant="ghost" className="min-h-8 px-2" disabled={last} onClick={() => change.mutate({ move: "down" })} aria-label={`Move “${name}” down`}>
            ↓
          </Button>
          <Button variant="ghost" className="min-h-8 px-2" onClick={() => change.mutate({ archived: !q.archived })} aria-label={`${q.archived ? "Bring back" : "Archive"} “${name}”`}>
            {q.archived ? "Bring back" : "Archive"}
          </Button>
        </div>
      )}
      <ErrorText error={change.error} />
    </li>
  );
}

function QuestionForm({
  start,
  sects,
  onSave,
  onCancel,
  saving,
  error,
}: {
  start?: BackstoryQuestionOut;
  sects: string[];
  onSave: (body: BackstoryQuestionIn) => void;
  onCancel: () => void;
  saving: boolean;
  error: unknown;
}) {
  const [kind, setKind] = useState<Kind>(start?.kind ?? "long");
  const [text, setText] = useState(start?.text ?? "");
  const [title, setTitle] = useState(start?.title ?? "");
  const [hint, setHint] = useState(start?.hint ?? "");
  const [optional, setOptional] = useState(start?.optional ?? false);
  const [options, setOptions] = useState(start?.kind === "choice" ? start.options.join("\n") : "");
  const [poles, setPoles] = useState<[string, string]>(start?.kind === "scale" ? [start.options[0] ?? "", start.options[1] ?? ""] : ["", ""]);
  const [condition, setCondition] = useState<Condition | null>(start?.condition ?? null);
  const shownKind = condition?.kind ?? "always";

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          kind,
          text,
          title,
          hint,
          optional: kind !== "heading" && optional,
          options: kind === "choice" ? options.split("\n").map((o) => o.trim()).filter(Boolean) : kind === "scale" ? poles : [],
          condition,
        });
      }}
    >
      <Field label="Question">
        <Textarea rows={2} required value={text} maxLength={5000} onChange={(e) => setText(e.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {(Object.keys(KINDS) as Kind[]).map((k) => (
              <option key={k} value={k}>
                {KINDS[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Short title" hint="Optional: the section's heading in the backstory, in place of the question.">
          <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        </Field>
      </div>
      {kind === "choice" && (
        <Field label="Options" hint="One a line.">
          <Textarea rows={4} required value={options} onChange={(e) => setOptions(e.target.value)} />
        </Field>
      )}
      {kind === "scale" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="One pole">
            <Input required value={poles[0]} maxLength={200} onChange={(e) => setPoles([e.target.value, poles[1]])} placeholder="Action" />
          </Field>
          <Field label="The other pole">
            <Input required value={poles[1]} maxLength={200} onChange={(e) => setPoles([poles[0], e.target.value])} placeholder="Intrigue" />
          </Field>
        </div>
      )}
      {kind !== "heading" && (
        <>
          <Field label="Hint" hint="Optional.">
            <Input value={hint} maxLength={5000} onChange={(e) => setHint(e.target.value)} />
          </Field>
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input type="checkbox" checked={optional} onChange={(e) => setOptional(e.target.checked)} />
            Optional
          </label>
        </>
      )}
      <Field label="Shown">
        <Select
          value={shownKind}
          onChange={(e) => {
            const v = e.target.value;
            setCondition(
              v === "social_age"
                ? { kind: "social_age", ages: ["Neonate"] }
                : v === "sect"
                  ? { kind: "sect", sects: sects.slice(0, 1) }
                  : v === "trait"
                    ? { kind: "trait", category: "backgrounds", name: "" }
                    : null,
            );
          }}
        >
          <option value="always">Always</option>
          <option value="social_age">By social age</option>
          <option value="sect">By sect</option>
          <option value="trait">With a trait on the sheet</option>
        </Select>
      </Field>
      {condition?.kind === "social_age" && (
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="mb-1 text-mist">For</legend>
          {AGES.map((age) => (
            <label key={age} className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                checked={condition.ages.includes(age)}
                onChange={(e) => setCondition({ ...condition, ages: e.target.checked ? [...condition.ages, age] : condition.ages.filter((a) => a !== age) })}
              />
              {age}
            </label>
          ))}
        </fieldset>
      )}
      {condition?.kind === "sect" && (
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="mb-1 text-mist">For</legend>
          {sects.map((sect) => (
            <label key={sect} className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                checked={condition.sects.includes(sect)}
                onChange={(e) => setCondition({ ...condition, sects: e.target.checked ? [...condition.sects, sect] : condition.sects.filter((x) => x !== sect) })}
              />
              {sect}
            </label>
          ))}
        </fieldset>
      )}
      {condition?.kind === "trait" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Trait kind">
            <Select value={condition.category} onChange={(e) => setCondition({ ...condition, category: e.target.value as "backgrounds" })}>
              <option value="backgrounds">Background</option>
              <option value="merits">Merit</option>
              <option value="flaws">Flaw</option>
            </Select>
          </Field>
          <Field label="Trait" hint="As the sheet names it, such as Alternate Identity or Dark Secret.">
            <Input required value={condition.name} maxLength={200} onChange={(e) => setCondition({ ...condition, name: e.target.value })} />
          </Field>
        </div>
      )}
      <ErrorText error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving}>
          Save the question
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
