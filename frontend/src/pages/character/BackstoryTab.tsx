import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { AnsweredSetOut, BackstoryOut, CharacterOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { headings } from "../../markdown";
import { Differences } from "./BackstoryDifferences";
import { BackstoryEditor } from "./BackstoryEditor";
import { backstoryStatus } from "./backstoryStatus";
import { BackstoryWizard } from "./BackstoryWizard";

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
 * The character's backstory: read, written in the editor, or built from the troupe's
 * questions, with the thread of staff feedback. Staff reading it send it back or
 * approve it here too.
 */
export function BackstoryTab({ character }: { character: CharacterOut }) {
  const backstory = useBackstory(character.id);
  const writer = !!backstory.data?.write;
  const questions = useBackstoryQuestions(character.id, !!backstory.data && (backstory.data.mode !== "free" || !writer));
  const [editingChoice, setEditing] = useState<boolean | null>(null);
  const [answering, setAnswering] = useState<boolean | null>(null);

  if (backstory.isPending) return <Loading />;
  if (backstory.error) return <ErrorText error={backstory.error} />;
  const b = backstory.data;
  // A draft not yet submitted opens in the editor, to carry on with.
  const editing = editingChoice ?? (writer && !!b.draft && character.status !== "retired");
  const sets = questions.data?.sets ?? [];
  const asked = writer && b.mode !== "free" && sets.length > 0;
  // Under "the wizard only", the player starts from the questions until a set is built.
  const wizardFirst = asked && b.mode === "wizard" && !sets.some((s) => s.built);
  const showWizard = asked && !editing && (answering ?? wizardFirst);
  const choosing = asked && b.mode === "either" && !b.written && answering === null && !editing;

  return (
    <div className="flex flex-col gap-4">
      <ReviewStatus backstory={b} asking={!!b.troupe_id && character.asking_troupe_id === b.troupe_id} />
      {writer && b.state === "returned" && <Resubmit characterId={character.id} drafted={!!b.draft} />}
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
        <BackstoryEditor characterId={character.id} backstory={b} onDone={() => setEditing(false)} />
      ) : (
        <BackstoryText
          backstory={b}
          note={
            asked &&
            b.written &&
            `Answering ${questions.data?.troupe_name ?? "the troupe"}'s questions again rebuilds the parts made from them; editing changes any of the text.`
          }
          drafted={writer && !!b.draft}
          actions={
            writer && (
              <div className="flex flex-wrap gap-2">
                {asked && (
                  <Button variant="secondary" onClick={() => setAnswering(true)}>
                    Answer the troupe's questions
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  {b.draft ? "Carry on writing" : b.written ? "Edit the backstory" : "Write the backstory"}
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

/** Where staff's reading of it stands, and what the person looking at it can do next. */
function ReviewStatus({ backstory: b, asking }: { backstory: BackstoryOut; asking: boolean }) {
  const dates = useDates();
  const by = [b.approved_by_name, b.approved_at && dates.date(b.approved_at)].filter(Boolean).join(", ");
  const status = backstoryStatus(b, by ? ` (${by})` : "", asking);
  if (!status) return null;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <Badge tone={status.tone}>{status.badge}</Badge>
      <span>{status.words}</span>
    </p>
  );
}

export function BackstoryText({
  backstory: b,
  actions,
  note,
  drafted = false,
  title = "Backstory",
}: {
  backstory: BackstoryOut;
  actions?: ReactNode;
  /** A line about the actions, under the title. */
  note?: ReactNode;
  /** Its writer has a draft, not yet submitted. */
  drafted?: boolean;
  title?: string;
}) {
  const dates = useDates();
  return (
    <Card title={title} actions={actions}>
      {note && <p className="mb-2 text-xs text-mist">{note}</p>}
      {drafted && (
        <div className="mb-3">
          <Notice>
            <Badge tone="gold">Draft, not yet submitted</Badge> You have a draft saved. This is the version the storytellers read until you submit it.
          </Notice>
        </div>
      )}
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

/** The player sends it back to staff once revised, with a reply. */
function Resubmit({ characterId, drafted }: { characterId: string; drafted: boolean }) {
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
        <Button onClick={() => send.mutate(undefined)} disabled={send.isPending || drafted}>
          Resubmit the backstory
        </Button>
        {drafted && <p className="self-center text-xs text-mist">Submit your draft first: the storytellers read the submitted version.</p>}
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

