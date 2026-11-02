import { useMutation, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useId, useReducer, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BackstoryOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, ErrorText, Field, Loading, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useLeaveWarning } from "../../hooks";
import { behind, opened, unsaved, writingReducer, type Writing } from "./backstoryDraft";
import { Differences } from "./BackstoryDifferences";

// Tiptap and ProseMirror come only with the editor, not with every character page.
const RichEditor = lazy(() => import("./RichEditor"));

/** The most a backstory holds (the API's cap), and how near it the editor starts counting down. */
export const MAX_LENGTH = 500_000;
const COUNT_FROM = 50_000;

/** How long typing has to stop for before the draft is saved. */
const AUTOSAVE_MS = 2000;

type View = "formatted" | "markdown";
const VIEW_KEY = "horatio.backstory.view";

function storedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "markdown" ? "markdown" : "formatted";
  } catch {
    return "formatted";
  }
}

function storeView(view: View) {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Remembering the choice is only a convenience.
  }
}

/** A draft as sent to the server, and the edit it goes up to. */
type Sent = { edit: number; text: string; basedOn: number };
const sent = (w: Writing): Sent => ({ edit: w.edit, text: w.text, basedOn: w.basedOn });

/**
 * Writing the backstory (issue #426): formatted, or as Markdown. A draft saves a
 * moment after typing stops and when the player switches away; it is not a version
 * until they submit it, and storytellers never read it. A version submitted
 * meanwhile (on another device, say) is shown beside the draft, and the player
 * chooses which to go on with.
 */
export function BackstoryEditor({ characterId, backstory, onDone }: { characterId: string; backstory: BackstoryOut; onDone: () => void }) {
  const path = { params: { path: { character_id: characterId } } };
  const key = ["backstory", characterId];
  const scope = { id: `backstory-${characterId}` };
  const client = useQueryClient();
  const dates = useDates();
  const hintId = useId();
  const [w, change] = useReducer(writingReducer, backstory, (b) => opened(b));
  const [view, setView] = useState<View>(storedView);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [comparing, setComparing] = useState(false);
  const [confirm, setConfirm] = useState<"theirs" | "discard" | null>(null);
  // Whatever the server sends is taken in, never over what was typed since the last save.
  useEffect(() => change({ type: "loaded", backstory }), [backstory]);

  // Saves wait on their own answer, not a refetch, and go one at a time, before a submission.
  const save = useMutation({
    scope,
    mutationFn: (s: Sent) => unwrap(api.PUT("/api/characters/{character_id}/backstory/draft", { ...path, body: { text: s.text, based_on: s.basedOn } })),
    onSuccess: (result, s) => {
      change({ type: "saved", edit: s.edit, version: result.version, draft: result.draft ?? null });
      setSavedAt(new Date());
      // A version was submitted elsewhere: fetch it, to show beside the draft.
      if (result.version > (client.getQueryData<BackstoryOut>(key)?.version ?? 0)) void client.invalidateQueries({ queryKey: key });
      client.setQueryData<BackstoryOut>(key, (old) => old && { ...old, draft: result.draft ?? null });
    },
  });
  const settled = (b: BackstoryOut) => {
    change({ type: "reset", backstory: b });
    client.setQueryData(key, b);
    // Elsewhere on the page (the review status, the feedback) follows.
    void client.invalidateQueries({ queryKey: ["backstory-standing", characterId] });
  };
  const submit = useMutation({
    scope,
    mutationFn: (s: Sent) => unwrap(api.PUT("/api/characters/{character_id}/backstory", { ...path, body: { text: s.text, version: s.basedOn } })),
    onSuccess: (b) => {
      settled(b);
      onDone();
    },
  });
  const discard = useMutation({
    scope,
    mutationFn: () => unwrap(api.DELETE("/api/characters/{character_id}/backstory/draft", path)),
    onSuccess: (b) => {
      settled(b);
      setConfirm(null);
      setComparing(false);
    },
  });

  const dirty = unsaved(w);
  const failed = save.isError && save.variables?.edit === w.edit;
  const saving = save.isPending;
  const busy = submit.isPending || discard.isPending;
  // For the timer and for leaving, which run after the render they were set up in.
  const latest = useRef({ w, inFlight: undefined as number | undefined, busy, mutate: save.mutate });
  useEffect(() => {
    latest.current = { w, inFlight: save.isPending ? save.variables?.edit : undefined, busy, mutate: save.mutate };
  });
  const saveNow = (always = false) => {
    const { w, inFlight, busy, mutate } = latest.current;
    if (busy || inFlight === w.edit || (!always && !unsaved(w))) return;
    mutate(sent(w));
  };

  // Autosave once typing stops. A save that failed isn't tried again until the next edit.
  useEffect(() => {
    if (!dirty || failed || saving || busy) return;
    const timer = setTimeout(saveNow, w.urgent ? 0 : AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [w.edit, dirty, failed, saving, busy]);
  // Save at once when the player switches away (a phone's other app) or leaves the page.
  useEffect(() => {
    const away = () => document.visibilityState === "hidden" && saveNow();
    document.addEventListener("visibilitychange", away);
    return () => {
      document.removeEventListener("visibilitychange", away);
      saveNow();
    };
  }, []);
  useLeaveWarning(dirty || saving);

  const submitNow = () => {
    // The draft first, so the server knows the submission is the draft and lets it go.
    if (dirty) save.mutate(sent(w));
    submit.mutate(sent(w));
  };
  const pick = (next: View) => {
    setView(next);
    storeView(next);
  };

  const late = behind(w);
  const drafted = w.text !== backstory.text || w.basedOn !== backstory.version;
  const left = MAX_LENGTH - w.text.length;
  const marks = w.text.includes("<!-- questions:") || backstory.edited_sets.length > 0;
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
  ) : (
    savedAt && `Saved ${dates.time(savedAt)}`
  );
  const hint =
    view === "formatted" ? (
      <>
        Use the buttons, or type Markdown as you go: # and a space for a heading, **bold**, - and a space for a list. Enter starts a new paragraph, Shift+Enter a new
        line.
      </>
    ) : (
      <>
        # for a heading, **bold**, *italic*, - for a list, [words](https://…) for a link. HTML is shown as written.
        {marks && " Lines like <!-- questions:… --> mark the sections built from the troupe's questions: answering again replaces what is between them, and keeps the rest."}
      </>
    );

  return (
    <Card
      title="Backstory"
      actions={
        <div className="flex gap-1" role="group" aria-label="Editor view">
          <Button variant={view === "formatted" ? "secondary" : "ghost"} aria-pressed={view === "formatted"} className="min-h-8 px-3" onClick={() => pick("formatted")}>
            Formatted
          </Button>
          <Button variant={view === "markdown" ? "secondary" : "ghost"} aria-pressed={view === "markdown"} className="min-h-8 px-3" onClick={() => pick("markdown")}>
            Markdown
          </Button>
        </div>
      }
    >
      {late && (
        <Behind
          backstory={backstory}
          comparing={comparing}
          onCompare={() => {
            // Compare what is typed now: saving it brings back the differences.
            if (!comparing) saveNow();
            setComparing(!comparing);
          }}
          onKeepMine={() => {
            change({ type: "keep mine", version: backstory.version });
            setComparing(false);
          }}
          confirming={confirm === "theirs"}
          onTakeTheirs={() => (confirm === "theirs" ? discard.mutate() : setConfirm("theirs"))}
          onCancel={() => setConfirm(null)}
          busy={busy}
        />
      )}
      {view === "formatted" ? (
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-mist" aria-hidden>
            Your backstory
          </span>
          <Suspense fallback={<Loading />}>
            <RichEditor key={w.loads} initial={w.text} label="Your backstory" describedBy={hintId} onChange={(text) => change({ type: "edit", text })} />
          </Suspense>
          <span id={hintId} className="text-xs text-mist">
            {hint}
          </span>
        </div>
      ) : (
        <Field label="Your backstory, in Markdown" hint={hint}>
          <Textarea rows={18} value={w.text} onChange={(e) => change({ type: "edit", text: e.target.value })} />
        </Field>
      )}
      {left < COUNT_FROM && (
        <p className={`mt-2 text-xs ${left < 5_000 ? "text-blood-bright" : "text-mist"}`}>
          {left >= 0 ? `${left.toLocaleString()} characters left` : `${(-left).toLocaleString()} characters over the limit`}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={submitNow} disabled={busy || late || !drafted || left < 0}>
          Submit the backstory
        </Button>
        {/* Closing saves what isn't saved yet, as leaving the editor any other way does. */}
        <Button variant="ghost" onClick={onDone}>
          Close
        </Button>
        <p className="text-xs text-mist" role="status" aria-live="polite">
          {status}
        </p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-mist">
        {drafted ? (
          <>
            <Badge tone="gold">Draft, not yet submitted</Badge>
            <span>Storytellers read only what you submit.</span>
            {!late &&
              (confirm === "discard" ? (
                <span className="flex flex-wrap items-center gap-2">
                  Throw away the changes since the last version?
                  <Button variant="danger" className="min-h-8 px-3" disabled={busy} onClick={() => discard.mutate()}>
                    Throw them away
                  </Button>
                  <Button variant="ghost" className="min-h-8 px-3" onClick={() => setConfirm(null)}>
                    Keep them
                  </Button>
                </span>
              ) : (
                <button type="button" className="underline hover:text-parchment pointer-coarse:py-2" onClick={() => setConfirm("discard")}>
                  Discard the draft
                </button>
              ))}
          </>
        ) : (
          <span>Your writing saves as a draft as you go. Submit it when it's ready for the storytellers.</span>
        )}
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <ErrorText error={submit.error} />
        <ErrorText error={discard.error} />
      </div>
    </Card>
  );
}

/** A newer version arrived since the draft was started: both are kept, and the player chooses. */
function Behind({
  backstory: b,
  comparing,
  onCompare,
  onKeepMine,
  confirming,
  onTakeTheirs,
  onCancel,
  busy,
}: {
  backstory: BackstoryOut;
  comparing: boolean;
  onCompare: () => void;
  onKeepMine: () => void;
  confirming: boolean;
  onTakeTheirs: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const dates = useDates();
  const when = [b.changed_at && dates.dateTime(b.changed_at), b.changed_by_name && `by ${b.changed_by_name}`].filter(Boolean).join(" ");
  const differences = b.draft?.behind ? b.draft.differences : null;
  return (
    <div className="mb-4 rounded-md border border-gold/40 bg-gold/10 p-3 text-sm" role="region" aria-label="A newer version">
      <p>
        A newer version was submitted{when ? ` ${when}` : ""}, after you started this draft, perhaps on another device. Your draft is kept: choose which to go on with.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="secondary" className="min-h-9 px-3" onClick={onKeepMine} disabled={busy}>
          Keep mine
        </Button>
        {confirming ? (
          <>
            <Button variant="danger" className="min-h-9 px-3" onClick={onTakeTheirs} disabled={busy}>
              Throw my draft away
            </Button>
            <Button variant="ghost" className="min-h-9 px-3" onClick={onCancel}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="secondary" className="min-h-9 px-3" onClick={onTakeTheirs} disabled={busy}>
            Take theirs
          </Button>
        )}
        <Button variant="ghost" className="min-h-9 px-3" aria-expanded={comparing} onClick={onCompare}>
          {comparing ? "Hide the comparison" : "Compare them"}
        </Button>
      </div>
      {comparing && (
        <div className="mt-3 flex flex-col gap-3">
          {differences ? (
            <Differences lines={differences} title="Your draft against the newer version" added="Only in your draft" removed="Only in the newer version" />
          ) : (
            <Loading />
          )}
          <details className="rounded-md border border-ash p-2">
            <summary className="cursor-pointer text-gold pointer-coarse:py-2">Read the newer version</summary>
            <div className="mt-2">
              <Markdown text={b.text} />
            </div>
          </details>
          <p className="text-xs text-mist">To bring a part of the newer version into your draft, copy it from here and paste it in, then keep yours.</p>
        </div>
      )}
    </div>
  );
}
