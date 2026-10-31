import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, ApiError, unwrap } from "../../api/client";
import type { AnsweredSetOut, BackstoryOut, CharacterOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { headings } from "../../markdown";
import { BackstoryWizard } from "./BackstoryWizard";

/** The most a backstory holds (the API's cap), and how near it the editor starts counting down. */
export const MAX_LENGTH = 500_000;
const COUNT_FROM = 50_000;

export function useBackstory(characterId: string, enabled = true) {
  return useQuery({
    queryKey: ["backstory", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/backstory", { params: { path: { character_id: characterId } } })),
    enabled,
  });
}

export function useBackstoryStanding(characterId: string, enabled = true) {
  return useQuery({
    queryKey: ["backstory-standing", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/backstory/standing", { params: { path: { character_id: characterId } } })),
    enabled,
  });
}

export function useBackstoryQuestions(characterId: string, enabled = true) {
  return useQuery({
    queryKey: ["backstory-questions", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/backstory/questions", { params: { path: { character_id: characterId } } })),
    enabled,
  });
}

/**
 * The character's backstory: read, written in Markdown, or built from the troupe's
 * questions, with the thread of staff feedback. Staff reading it send it back or
 * approve it here too.
 */
export function BackstoryTab({ character }: { character: CharacterOut }) {
  const backstory = useBackstory(character.id);
  const writer = !!backstory.data?.write;
  const questions = useBackstoryQuestions(character.id, !!backstory.data && (backstory.data.mode !== "free" || !writer));
  const [editing, setEditing] = useState(false);
  const [answering, setAnswering] = useState<boolean | null>(null);

  if (backstory.isPending) return <Loading />;
  if (backstory.error) return <ErrorText error={backstory.error} />;
  const b = backstory.data;
  const sets = questions.data?.sets ?? [];
  const asked = writer && b.mode !== "free" && sets.length > 0;
  // Under "the wizard only", the player starts from the questions until a set is built.
  const wizardFirst = asked && b.mode === "wizard" && !sets.some((s) => s.built);
  const showWizard = asked && !editing && (answering ?? wizardFirst);
  const choosing = asked && b.mode === "either" && !b.written && answering === null && !editing;

  return (
    <div className="flex flex-col gap-4">
      <ReviewStatus backstory={b} />
      {writer && b.state === "returned" && <Resubmit characterId={character.id} />}
      {choosing ? (
        <Card title="Backstory">
          <p className="mb-3 text-sm">{questions.data?.troupe_name} lets you write your backstory freely, or build it by answering its questions.</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setEditing(true)}>Write freely</Button>
            <Button variant="secondary" onClick={() => setAnswering(true)}>
              Answer the troupe's questions
            </Button>
          </div>
        </Card>
      ) : showWizard ? (
        <BackstoryWizard
          characterId={character.id}
          sets={sets}
          troupeName={questions.data?.troupe_name ?? ""}
          edited={b.edited_sets}
          onBuilt={() => setAnswering(false)}
          onClose={b.written ? () => setAnswering(false) : undefined}
        />
      ) : editing ? (
        <BackstoryEditor key={b.version} characterId={character.id} backstory={b} onDone={() => setEditing(false)} />
      ) : (
        <BackstoryText
          backstory={b}
          actions={
            writer && (
              <div className="flex flex-wrap gap-2">
                {asked && (
                  <Button variant="ghost" onClick={() => setAnswering(true)}>
                    Answer the troupe's questions
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  {b.written ? "Edit the backstory" : "Write the backstory"}
                </Button>
              </div>
            )
          }
        />
      )}
      {b.thread.length > 0 && <Thread backstory={b} />}
      {b.review && <BackstoryReview characterId={character.id} backstory={b} />}
      {!writer && <Answers sets={sets} />}
    </div>
  );
}

/** Where staff's reading of it stands, for the player and staff alike. */
function ReviewStatus({ backstory: b }: { backstory: BackstoryOut }) {
  const dates = useDates();
  if (!b.troupe_name) return null;
  const words =
    b.changed_since_approval
      ? `Changed since ${b.troupe_name} approved it.`
      : b.approved
        ? `Approved by ${b.troupe_name}${b.approved_by_name ? ` (${b.approved_by_name}` : ""}${b.approved_at ? `, ${dates.date(b.approved_at)})` : b.approved_by_name ? ")" : ""}.`
        : b.state === "returned"
          ? `${b.troupe_name} sent it back with feedback.`
          : b.state === "resubmitted"
            ? `Revised and back with ${b.troupe_name}'s storytellers.`
            : b.required
              ? `${b.troupe_name} needs it approved before accepting the character.`
              : `${b.troupe_name}'s storytellers read it.`;
  const tone = b.approved ? "mist" : b.state === "returned" || b.changed_since_approval ? "blood" : "gold";
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <Badge tone={tone}>{b.approved ? "approved" : b.changed_since_approval ? "changed" : b.state === "none" ? "not yet approved" : b.state}</Badge>
      <span>{words}</span>
    </p>
  );
}

export function BackstoryText({ backstory: b, actions, title = "Backstory" }: { backstory: BackstoryOut; actions?: ReactNode; title?: string }) {
  const dates = useDates();
  return (
    <Card title={title} actions={actions}>
      {b.changed_at && (
        <p className="mb-3 text-xs text-mist">
          Last changed {dates.date(b.changed_at)}
          {b.changed_by_name ? ` by ${b.changed_by_name}` : ""}
        </p>
      )}
      {b.written ? <Markdown text={b.text} /> : <Empty>Nothing written yet.</Empty>}
    </Card>
  );
}

/** Writing it, in Markdown, with a preview. It saves only on Save, and never over a newer version. */
function BackstoryEditor({ characterId, backstory, onDone }: { characterId: string; backstory: BackstoryOut; onDone: () => void }) {
  const [draft, setDraft] = useState(backstory.text);
  const [preview, setPreview] = useState(false);
  const client = useQueryClient();
  const save = useAction(async () => {
    await unwrap(
      api.PUT("/api/characters/{character_id}/backstory", { params: { path: { character_id: characterId } }, body: { text: draft, version: backstory.version } }),
    );
    onDone();
  });
  const stale = save.error instanceof ApiError && save.error.status === 409;
  const left = MAX_LENGTH - draft.length;

  return (
    <Card
      title="Backstory"
      actions={
        <div className="flex gap-1" role="group" aria-label="Editor view">
          <Button variant={preview ? "ghost" : "secondary"} aria-pressed={!preview} className="min-h-8 px-3" onClick={() => setPreview(false)}>
            Write
          </Button>
          <Button variant={preview ? "secondary" : "ghost"} aria-pressed={preview} className="min-h-8 px-3" onClick={() => setPreview(true)}>
            Preview
          </Button>
        </div>
      }
    >
      {preview ? (
        <div className="min-h-40 rounded-md border border-ash p-3">{draft.trim() ? <Markdown text={draft} /> : <Empty>Nothing to preview yet.</Empty>}</div>
      ) : (
        <Field
          label="Your backstory, in Markdown"
          hint={
            <>
              # for a heading, **bold**, *italic*, - for a list, [words](https://…) for a link. HTML is shown as written.
              {backstory.edited_sets.length > 0 || backstory.text.includes("<!-- questions:")
                ? " Lines like <!-- questions:… --> mark the sections built from the troupe's questions: answering again replaces what is between them, and keeps the rest."
                : ""}
            </>
          }
        >
          <Textarea rows={18} value={draft} maxLength={MAX_LENGTH} onChange={(e) => setDraft(e.target.value)} />
        </Field>
      )}
      {left < COUNT_FROM && (
        <p className={`mt-2 text-xs ${left < 5_000 ? "text-blood-bright" : "text-mist"}`}>{left.toLocaleString()} characters left</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={() => save.mutate(undefined)} disabled={save.isPending || draft === backstory.text}>
          Save the backstory
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <div className="mt-3">
        <ErrorText error={save.error} />
        {stale && (
          <Button
            variant="secondary"
            className="mt-2"
            onClick={async () => {
              await client.invalidateQueries({ queryKey: ["backstory", characterId] });
              onDone();
            }}
          >
            Load the newer version (your changes here are lost)
          </Button>
        )}
      </div>
    </Card>
  );
}

/** The player sends it back to staff once revised, with a reply. */
function Resubmit({ characterId }: { characterId: string }) {
  const [note, setNote] = useState("");
  const send = useAction(() =>
    unwrap(api.POST("/api/characters/{character_id}/backstory/resubmit", { params: { path: { character_id: characterId } }, body: { note } })),
  );
  return (
    <Card title="Sent back to you">
      <p className="mb-3 text-sm">Revise the backstory as the feedback below asks, then send it back to the storytellers.</p>
      <Field label="Reply to the storytellers" hint="Optional.">
        <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => send.mutate(undefined)} disabled={send.isPending}>
          Resubmit the backstory
        </Button>
      </div>
      <ErrorText error={send.error} />
    </Card>
  );
}

/** Feedback, replies and approvals, oldest first. */
export function Thread({ backstory: b }: { backstory: BackstoryOut }) {
  const dates = useDates();
  return (
    <Card title="Feedback">
      <ol className="flex flex-col gap-3" aria-label="Feedback and replies">
        {b.thread.map((e) => (
          <li key={e.id} className={`rounded-md border p-3 text-sm ${e.kind === "feedback" ? "border-gold/40" : "border-ash"}`}>
            <p className="mb-1 text-xs text-mist">
              {e.author_name}, {dates.dateTime(e.at)}
              {e.kind === "feedback" && (e.section ? ` · on “${e.section}”` : " · on the whole backstory")}
              {e.kind === "approved" && " · approved it"}
              {e.kind === "reply" && " · resubmitted it"}
            </p>
            {e.body && <p className="whitespace-pre-line">{e.body}</p>}
          </li>
        ))}
      </ol>
    </Card>
  );
}

/**
 * Staff's part: what changed since they approved it, sending it back with feedback
 * (overall or on a section), and approving it.
 */
export function BackstoryReview({ characterId, backstory: b }: { characterId: string; backstory: BackstoryOut }) {
  const [section, setSection] = useState("");
  const [body, setBody] = useState("");
  const [note, setNote] = useState("");
  const sections = headings(b.text);
  const path = { params: { path: { character_id: characterId } } };
  const feedback = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/backstory/feedback", { ...path, body: { body, section } }));
    setBody("");
  });
  const approve = useAction(() => unwrap(api.POST("/api/characters/{character_id}/backstory/approve", { ...path, body: { version: b.version, note } })));

  return (
    <Card title="Your reading">
      {b.changed_since_approval && b.differences && <Differences lines={b.differences} />}
      <div className="flex flex-col gap-3">
        <Field label="Feedback on">
          <Select value={section} onChange={(e) => setSection(e.target.value)}>
            <option value="">The whole backstory</option>
            {sections.map((h, i) => (
              <option key={`${i}-${h}`} value={h}>
                {h}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Feedback for the player" hint="Sends the backstory back to them, without declining the character.">
          <Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        <div>
          <Button variant="secondary" onClick={() => feedback.mutate(undefined)} disabled={feedback.isPending || !body.trim()}>
            Send back with feedback
          </Button>
        </div>
        <ErrorText error={feedback.error} />
        {!b.approved && (
          <>
            <Field label="Note with the approval" hint="Optional.">
              <Textarea rows={1} value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            <div>
              <Button onClick={() => approve.mutate(undefined)} disabled={approve.isPending || !b.written}>
                {b.changed_since_approval ? "Approve it again" : "Approve the backstory"}
              </Button>
            </div>
            <ErrorText error={approve.error} />
          </>
        )}
      </div>
    </Card>
  );
}

/** What changed since it was approved, line by line. */
function Differences({ lines }: { lines: NonNullable<BackstoryOut["differences"]> }) {
  return (
    <div className="mb-4">
      <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Changed since it was approved</h3>
      <div className="overflow-x-auto rounded-md border border-ash bg-night p-2 font-mono text-xs" aria-label="Changes since it was approved">
        {lines.map((line, i) =>
          line.change === "skipped" ? (
            <p key={i} className="py-1 text-mist italic">
              … {line.count} unchanged lines …
            </p>
          ) : (
            <p
              key={i}
              className={`whitespace-pre-wrap ${line.change === "added" ? "bg-gold/15 text-parchment" : line.change === "removed" ? "bg-blood/20 text-mist line-through" : "text-mist"}`}
            >
              <span aria-hidden>{line.change === "added" ? "+ " : line.change === "removed" ? "− " : "  "}</span>
              <span className="sr-only">{line.change === "added" ? "Added: " : line.change === "removed" ? "Removed: " : ""}</span>
              {line.text || " "}
            </p>
          ),
        )}
      </div>
    </div>
  );
}

/** The troupe's questions as the player answered them, for staff. */
export function Answers({ sets }: { sets: AnsweredSetOut[] }) {
  if (!sets.length) return null;
  return (
    <Card title="Answers to the troupe's questions">
      <div className="flex flex-col gap-4">
        {sets.map((s) => (
          <details key={s.id} className="group">
            <summary className="cursor-pointer text-sm text-gold">{s.name}</summary>
            <dl className="mt-2 flex flex-col gap-3 text-sm">
              {s.questions.map((q) =>
                q.kind === "heading" ? (
                  <h3 key={q.id} className="mt-2 text-base text-gold">
                    {q.text}
                  </h3>
                ) : (
                  <div key={q.id}>
                    <dt className="text-mist">
                      {q.text}
                      {q.archived && <span className="ml-2 text-xs">(archived)</span>}
                    </dt>
                    <dd className="whitespace-pre-line">{q.answer_text}</dd>
                  </div>
                ),
              )}
            </dl>
          </details>
        ))}
      </div>
    </Card>
  );
}

