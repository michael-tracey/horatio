import { describe, expect, it } from "vitest";
import type { FeedingIn, MyDowntime, QuestionOut } from "../../api/types";
import { EMPTY_FORM, type Form, formReducer, toAnswers, unsaved } from "./downtimeForm";

const question = (id: string, kind = "action"): QuestionOut => ({ id, kind, action_kind: kind === "action" ? "general" : null }) as QuestionOut;
const feeding = (where: string): FeedingIn => ({ actions: 0, where, gifts: [], herd_own: 0, herd_saved: 0, herd_other: 0, herd_other_text: "", resonance: "", territory: "", patrols: [] });

/** The downtime as the server sends it, with these answers by question. */
function server(answers: Record<string, string[]>, where = ""): MyDowntime {
  return {
    questions: [question("hunt"), question("story", "custom")],
    answers: Object.entries(answers).flatMap(([question_id, bodies]) => bodies.map((body, i) => ({ question_id, slot: i + 1, body, structured: {} }))),
    feeding: { answer: feeding(where) },
  } as unknown as MyDowntime;
}

const typed = (form: Form, question: string, ...bodies: string[]) =>
  formReducer(form, { type: "answers", question, answers: bodies.map((body) => ({ body })) });

describe("the downtime form", () => {
  it("takes the server's answers on the first load", () => {
    const form = formReducer(EMPTY_FORM, { type: "loaded", downtime: server({ hunt: ["Docks"] }) });
    expect(form.draft).toEqual({ hunt: [{ body: "Docks", structured: {} }], story: [{ body: "" }] });
    expect(form.feeding).toEqual(feeding(""));
    expect(unsaved(form)).toBe(false);
  });

  it("keeps a part edited since the last save when a refetch brings something else", () => {
    let form = formReducer(EMPTY_FORM, { type: "loaded", downtime: server({ hunt: ["Docks"] }) });
    form = typed(form, "hunt", "Docks, then the river");
    form = formReducer(form, { type: "feeding", feeding: feeding("The Rack") });
    // Elsewhere, the story was written and the hunt changed.
    form = formReducer(form, { type: "loaded", downtime: server({ hunt: ["Somewhere else"], story: ["From my phone"] }, "Elsewhere") });
    expect(form.draft.hunt).toEqual([{ body: "Docks, then the river" }]);
    expect(form.draft.story).toEqual([{ body: "From my phone", structured: {} }]);
    expect(form.feeding).toEqual(feeding("The Rack"));
    expect(unsaved(form)).toBe(true);
  });

  it("keeps typing done while a save was on its way, and takes the rest once saved", () => {
    let form = formReducer(EMPTY_FORM, { type: "loaded", downtime: server({}) });
    form = typed(form, "hunt", "Docks");
    const sent = form.version;
    form = typed(form, "hunt", "Docks and more");
    form = formReducer(form, { type: "saved", version: sent });
    form = formReducer(form, { type: "loaded", downtime: server({ hunt: ["Docks"] }) });
    expect(form.draft.hunt).toEqual([{ body: "Docks and more" }]);
    expect(unsaved(form)).toBe(true);
    form = formReducer(form, { type: "saved", version: form.version });
    expect(unsaved(form)).toBe(false);
  });

  it("keeps the space just typed and an empty action box when the server trims them away", () => {
    let form = formReducer(EMPTY_FORM, { type: "loaded", downtime: server({}) });
    form = typed(form, "hunt", "Docks ", "");
    form = formReducer(form, { type: "saved", version: form.version });
    form = formReducer(form, { type: "loaded", downtime: server({ hunt: ["Docks"] }) });
    expect(form.draft.hunt).toEqual([{ body: "Docks " }, { body: "" }]);
    expect(toAnswers(form.draft).map((a) => a.body)).toEqual(["Docks ", "", ""]);
  });
});
