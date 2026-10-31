import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, ApiError, unwrap } from "../../api/client";
import type { AnsweredQuestionOut, AnsweredSetOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Input, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

/** A point on a scale between two poles, in words, as the server writes it into the backstory. */
export function scaleLabel(value: number, [a, b]: string[]): string {
  return [a, `More ${a} than ${b}`, `Evenly ${a} and ${b}`, `More ${b} than ${a}`, b][value - 1] ?? "";
}

/**
 * Answering the troupe's backstory questions, one set at a time. Each answer saves
 * as the player leaves it, so a draft can be left and come back to. Building a set
 * writes its answers into the backstory, one section each.
 */
export function BackstoryWizard({
  characterId,
  sets,
  troupeName,
  edited,
  onBuilt,
  onClose,
}: {
  characterId: string;
  sets: AnsweredSetOut[];
  troupeName: string;
  edited: string[];
  onBuilt: () => void;
  onClose?: () => void;
}) {
  const [setId, setSetId] = useState(sets.find((s) => !s.built)?.id ?? sets[0]!.id);
  const current = sets.find((s) => s.id === setId) ?? sets[0]!;
  const [given, setGiven] = useState<Record<string, string>>(() => Object.fromEntries(sets.flatMap((s) => s.questions.map((q) => [q.id, q.answer]))));
  const [saved, setSaved] = useState<Record<string, string>>(given);
  const pending = useRef(new Set<Promise<unknown>>());
  const [confirming, setConfirming] = useState(false);

  const answer = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      unwrap(
        api.PUT("/api/characters/{character_id}/backstory/answers/{question_id}", {
          params: { path: { character_id: characterId, question_id: id } },
          body: { answer: value },
        }),
      ),
    onSuccess: (kept) => setSaved((now) => ({ ...now, [kept.question_id]: kept.answer })),
  });
  const keep = (id: string, value: string) => {
    if (value === saved[id]) return;
    const sent = answer.mutateAsync({ id, value }).catch(() => undefined);
    pending.current.add(sent);
    void sent.finally(() => pending.current.delete(sent));
  };
  const build = useAction(async (replace: boolean) => {
    await Promise.all(pending.current);
    await unwrap(
      api.POST("/api/characters/{character_id}/backstory/sets/{set_id}/build", {
        params: { path: { character_id: characterId, set_id: current.id } },
        body: { replace_edits: replace },
      }),
    );
    setConfirming(false);
    onBuilt();
  });
  const editedHere = edited.includes(current.id);
  const unsaved = Object.keys(given).some((id) => (given[id] ?? "") !== (saved[id] ?? ""));

  return (
    <Card
      title={`${troupeName}'s questions`}
      actions={
        onClose && (
          <Button variant="ghost" onClick={onClose}>
            Back to the backstory
          </Button>
        )
      }
    >
      {sets.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Question sets">
          {sets.map((s) => (
            <Button key={s.id} variant={s.id === current.id ? "secondary" : "ghost"} aria-pressed={s.id === current.id} onClick={() => setSetId(s.id)}>
              {s.name}
              {s.built && <Badge>built</Badge>}
            </Button>
          ))}
        </div>
      )}
      <p className="mb-4 text-sm text-mist">
        Your answers save as you go: you can leave and come back. Building writes each answer into your backstory as its own section, which you can then edit
        freely.
      </p>
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (editedHere) setConfirming(true);
          else
            build.mutate(false, {
              // Edited since, on another device: ask first.
              onError: (error) => setConfirming(error instanceof ApiError && error.status === 409),
            });
        }}
      >
        {current.questions.map((q) => (
          <Question key={q.id} question={q} value={given[q.id] ?? ""} onChange={(v) => setGiven((now) => ({ ...now, [q.id]: v }))} onLeave={(v) => keep(q.id, v)} />
        ))}
        <p className="text-xs text-mist" aria-live="polite">
          {answer.isPending ? "Saving…" : unsaved ? "" : "All answers saved."}
        </p>
        <ErrorText error={answer.error} />
        {confirming ? (
          <div className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/10 p-3 text-sm">
            <p>You have edited the sections built from {current.name} since. Building again replaces them; your writing outside them stays.</p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => build.mutate(true)} disabled={build.isPending}>
                Replace my edits
              </Button>
              <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                Keep them
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <Button type="submit" disabled={build.isPending}>
              Build the backstory from {current.name}
            </Button>
          </div>
        )}
        <ErrorText error={confirming ? null : build.error} />
      </form>
    </Card>
  );
}

function Question({ question: q, value, onChange, onLeave }: { question: AnsweredQuestionOut; value: string; onChange: (value: string) => void; onLeave: (value: string) => void }) {
  if (q.kind === "heading") return <h3 className="mt-2 border-b border-ash pb-1 text-lg text-gold">{q.text}</h3>;
  const label = (
    <span className="text-parchment">
      {q.text}
      {q.optional && <span className="ml-2 text-xs text-mist">(optional)</span>}
    </span>
  );
  const hint = q.hint && <span className="text-xs text-mist">{q.hint}</span>;
  if (q.kind === "choice" || q.kind === "scale") {
    const options = q.kind === "choice" ? q.options.map((o) => [o, o]) : [1, 2, 3, 4, 5].map((n) => [String(n), scaleLabel(n, q.options)]);
    const pick = (v: string) => {
      onChange(v);
      onLeave(v);
    };
    return (
      <fieldset className="flex flex-col gap-2 text-sm">
        <legend className="mb-1">{label}</legend>
        {hint}
        <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 ${q.kind === "scale" ? "max-sm:flex-col max-sm:items-start" : ""}`}>
          {q.kind === "scale" && <span className="text-mist max-sm:hidden">{q.options[0]}</span>}
          {options.map(([v, words]) => (
            <label key={v} className="flex min-h-10 items-center gap-2">
              <input type="radio" name={q.id} value={v} checked={value === v} onChange={() => pick(v!)} aria-label={q.kind === "scale" ? words : undefined} />
              <span className={q.kind === "scale" ? "sm:sr-only" : ""}>{words}</span>
            </label>
          ))}
          {q.kind === "scale" && <span className="text-mist max-sm:hidden">{q.options[1]}</span>}
        </div>
        {value && q.optional && (
          <button type="button" className="self-start text-xs text-mist underline" onClick={() => pick("")}>
            Clear
          </button>
        )}
      </fieldset>
    );
  }
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      {hint}
      {q.kind === "long" ? (
        <Textarea rows={4} value={value} onChange={(e) => onChange(e.target.value)} onBlur={(e) => onLeave(e.target.value)} />
      ) : (
        <Input
          value={value}
          inputMode={q.kind === "year" ? "numeric" : undefined}
          maxLength={q.kind === "year" ? 4 : 2000}
          placeholder={q.kind === "year" ? "YYYY" : undefined}
          className={q.kind === "year" ? "w-28" : undefined}
          onChange={(e) => onChange(e.target.value)}
          onBlur={(e) => onLeave(e.target.value)}
        />
      )}
    </label>
  );
}
