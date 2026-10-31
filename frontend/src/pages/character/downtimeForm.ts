import type { AnswerIn, FeedingIn, MyDowntime } from "../../api/types";

/** The answers to each question on the form, by question id, in slot order. */
export type Draft = Record<string, { body: string; structured?: Record<string, unknown> }[]>;
export type Answers = Draft[string];

/** The edit key of the Feeding section, beside the question ids. */
export const FEEDING = "feeding";

/**
 * The downtime form as the player has it. Edits are numbered as they are made,
 * so a part the player changed since the server last took their answers is
 * known, and is never replaced by what a refetch brings.
 */
export type Form = {
  draft: Draft;
  feeding: FeedingIn | null;
  /** The number of the edit each part last changed at, by question id or FEEDING. */
  edited: Record<string, number>;
  /** The number of the latest edit. */
  version: number;
  /** The latest edit the server has taken. */
  saved: number;
};

export type FormChange =
  | { type: "loaded"; downtime: MyDowntime }
  | { type: "answers"; question: string; answers: Answers }
  | { type: "feeding"; feeding: FeedingIn }
  | { type: "saved"; version: number };

export const EMPTY_FORM: Form = { draft: {}, feeding: null, edited: {}, version: 0, saved: 0 };

/** Whether there are edits the server doesn't have yet. */
export const unsaved = (form: Form) => form.version > form.saved;

export function toDraft(downtime: MyDowntime): Draft {
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

export function toAnswers(draft: Draft): AnswerIn[] {
  return Object.entries(draft).flatMap(([question_id, answers]) =>
    answers.map((a, i) => ({ question_id, slot: i + 1, body: a.body, structured: a.structured ?? null })),
  );
}

/** JSON with object keys sorted and empty values left out, so two that mean the same compare equal. */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v)
            .filter(([, x]) => x !== undefined && x !== null)
            .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
        )
      : v,
  );
}

/** Answers as the server keeps them: trimmed, the blank ones dropped. */
function kept(answers: Answers): Answers {
  return answers
    .filter((a) => a.body.trim() || canonical(a.structured ?? {}) !== "{}")
    .map((a) => ({ body: a.body.trim(), structured: a.structured ?? {} }));
}

const sameAnswers = (a: Answers, b: Answers) => canonical(kept(a)) === canonical(kept(b));

/**
 * The form once the server's answers have come (a load, a save's answer or a
 * refetch). A part edited since the last save stays as the player has it. So does
 * a part that says the same as the server's, so the space just typed at the end of
 * a line isn't trimmed away, nor an empty action box dropped. Any other part
 * takes the server's, which may have changed elsewhere.
 */
function loaded(form: Form, downtime: MyDowntime): Form {
  const mine = (key: string) => (form.edited[key] ?? 0) > form.saved;
  const draft: Draft = {};
  for (const [question, theirs] of Object.entries(toDraft(downtime))) {
    const ours = form.draft[question];
    draft[question] = ours && (mine(question) || sameAnswers(ours, theirs)) ? ours : theirs;
  }
  const theirs = downtime.feeding?.answer ?? null;
  const feeding = theirs && form.feeding && (mine(FEEDING) || canonical(form.feeding) === canonical(theirs)) ? form.feeding : theirs;
  return { ...form, draft, feeding };
}

export function formReducer(form: Form, change: FormChange): Form {
  const version = form.version + 1;
  switch (change.type) {
    case "loaded":
      return loaded(form, change.downtime);
    case "answers":
      return {
        ...form,
        draft: { ...form.draft, [change.question]: change.answers },
        edited: { ...form.edited, [change.question]: version },
        version,
      };
    case "feeding":
      return { ...form, feeding: change.feeding, edited: { ...form.edited, [FEEDING]: version }, version };
    case "saved":
      return { ...form, saved: Math.max(form.saved, change.version) };
  }
}
