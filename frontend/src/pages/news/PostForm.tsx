import { lazy, Suspense, useId, useRef, useState } from "react";
import type { AgencyOut, PostOut } from "../../api/types";
import { DateInput } from "../../components/DateInput";
import { Button, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { KINDS, scheduleProblem, suggestedTime, type Kind } from "./posts";
import { DiscordPreview, StoryView } from "./Story";

const RichEditor = lazy(() => import("../character/RichEditor"));

export const MAX_BYTES = 10 * 1024 * 1024;
export const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

export type Fields = { agency_id: string | null; title: string; dateline: string; body: string };

/** What the writer asked for: save it as it is, send it as a proposal, publish it, schedule it, or decline a proposal. */
export type Action = { do: "draft" } | { do: "save" } | { do: "propose" } | { do: "publish"; note: string } | { do: "schedule"; at: string } | { do: "decline"; note: string };

/**
 * Writing a post (#510): its agency, headline, dateline, body in the rich text editor,
 * and picture, with a preview as players and Discord will show it. What it can do
 * next depends on who writes and where it stands: storytellers and assistant
 * storytellers save drafts, publish and schedule (on their own clock), and take up or
 * decline narrators' proposals; a narrator only sends a proposal and changes it while
 * it waits. A published post is changed in place.
 */
export function PostForm({
  kind,
  post,
  writes,
  agencies,
  busy = false,
  error,
  onAction,
  onPicture,
  onRemovePicture,
  onCancel,
}: {
  kind: Kind;
  post?: PostOut;
  writes: boolean;
  agencies: AgencyOut[];
  busy?: boolean;
  error?: unknown;
  onAction: (fields: Fields, action: Action) => void;
  onPicture: (fields: Fields, file: File) => void;
  onRemovePicture: () => void;
  onCancel: () => void;
}) {
  const dates = useDates();
  const words = KINDS[kind];
  const usable = agencies.filter((a) => !a.retired || a.id === post?.agency_id);
  const [fields, setFields] = useState<Fields>({
    agency_id: post?.agency_id ?? (usable.length === 1 ? usable[0]!.id : null),
    title: post?.title ?? "",
    dateline: post?.dateline ?? "",
    body: post?.body ?? "",
  });
  const set = (change: Partial<Fields>) => setFields((f) => ({ ...f, ...change }));
  const [view, setView] = useState<"write" | "preview">("write");
  const [when, setWhen] = useState(() => (post?.publish_at ? dates.toInput(post.publish_at) : ""));
  const [scheduling, setScheduling] = useState(post?.status === "scheduled");
  const [declining, setDeclining] = useState(false);
  const [note, setNote] = useState("");
  const [tooBig, setTooBig] = useState(false);
  const [missing, setMissing] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const bodyHint = useId();

  const status = post?.status;
  const published = status === "published";
  const proposal = status === "proposed";
  const agency = agencies.find((a) => a.id === fields.agency_id);
  const problem = scheduling ? scheduleProblem(when, when ? dates.fromInput(when) : null) : null;

  /** Act, once what it needs is there: a headline, and for news an agency. */
  const act = (action: Action) => {
    const lacking = !fields.title.trim() ? "Write a headline." : kind === "news" && !fields.agency_id ? "Choose the agency it comes from." : null;
    setMissing(lacking);
    if (!lacking) onAction({ ...fields, title: fields.title.trim() }, action);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1" role="group" aria-label="Writing or preview">
        <Button variant={view === "write" ? "secondary" : "ghost"} aria-pressed={view === "write"} className="min-h-8 px-3" onClick={() => setView("write")}>
          Write
        </Button>
        <Button variant={view === "preview" ? "secondary" : "ghost"} aria-pressed={view === "preview"} className="min-h-8 px-3" onClick={() => setView("preview")}>
          Preview
        </Button>
      </div>

      {view === "preview" ? (
        <div className="flex flex-col gap-4">
          <h3 className="text-sm text-mist">As players will read it</h3>
          <StoryView post={{ ...fields, picture: post?.picture ?? null, published_at: null }} agency={agency} />
          <h3 className="text-sm text-mist">Roughly as it will look on Discord</h3>
          <DiscordPreview post={{ ...fields, picture: post?.picture ?? null }} agency={agency} />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {kind === "news" && (
            <Field label="Agency" hint={usable.length === 0 ? "Make an agency first, under Customise › News." : undefined}>
              <Select value={fields.agency_id ?? ""} onChange={(e) => set({ agency_id: e.target.value || null })}>
                <option value="">Choose an agency…</option>
                {usable.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                    {a.retired ? " (retired)" : ""}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Headline">
            <Input value={fields.title} maxLength={200} onChange={(e) => set({ title: e.target.value })} />
          </Field>
          {kind === "news" && (
            <Field label="Dateline (optional)" hint="An in-world date or place, shown above the story: “Boston, the night of the 3rd”.">
              <Input value={fields.dateline} maxLength={200} onChange={(e) => set({ dateline: e.target.value })} />
            </Field>
          )}
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-mist" aria-hidden>
              The {words.noun}
            </span>
            <Suspense fallback={<Loading />}>
              <RichEditor initial={fields.body} label={`The ${words.noun}`} describedBy={bodyHint} placeholder={`Write the ${words.noun} here…`} onChange={(body) => set({ body })} />
            </Suspense>
            <span id={bodyHint} className="text-xs text-mist">
              Headings, bold, italics, lists, quotes and links show in Horatio and on Discord.
            </span>
          </div>
          <div className="flex flex-col gap-2 text-sm">
            <span className="text-mist">Picture (optional)</span>
            {post?.picture && <img src={`${post.picture}/600.webp`} alt="The picture" className="max-h-48 w-fit rounded-md border border-ash" />}
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPT}
              aria-label="Choose a picture"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                setTooBig(file.size > MAX_BYTES);
                if (file.size <= MAX_BYTES) onPicture(fields, file);
              }}
            />
            <span className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" disabled={busy} onClick={() => fileInput.current?.click()}>
                {post?.picture ? "Choose another picture" : "Add a picture"}
              </Button>
              {post?.picture && (
                <Button type="button" variant="ghost" disabled={busy} onClick={onRemovePicture}>
                  Remove the picture
                </Button>
              )}
            </span>
            {!post && <span className="text-xs text-mist">Adding a picture saves the {words.noun} {writes ? "as a draft" : "as your proposal"} first.</span>}
            {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
          </div>
        </div>
      )}

      {writes && proposal && post?.proposed_by && (
        <Field label={`Note to ${post.proposed_by} (optional)`} hint="Sent with Publish now or Decline.">
          <Textarea rows={2} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
        </Field>
      )}

      {writes && scheduling && !published && (
        <div className="flex flex-col gap-2 rounded-md border border-ash p-3">
          <Field label={`Publish at (${dates.zoneName(when ? dates.fromInput(when) : new Date())})`} hint="It goes out within a minute of then, in the app and on Discord.">
            <DateInput type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </Field>
          {problem && when && <p className="text-sm text-blood-bright">{problem}</p>}
          <span className="flex flex-wrap gap-2">
            <Button disabled={busy || !!problem} onClick={() => act({ do: "schedule", at: dates.fromInput(when).toISOString() })}>
              {status === "scheduled" ? "Save and keep it scheduled" : "Schedule"}
            </Button>
            {status !== "scheduled" && (
              <Button variant="ghost" onClick={() => setScheduling(false)}>
                Not now
              </Button>
            )}
          </span>
        </div>
      )}

      {declining && (
        <div className="flex flex-col gap-2 rounded-md border border-blood/60 p-3 text-sm">
          <p>Decline this proposal? {post?.proposed_by ?? "The narrator"} is told{note ? ", with your note" : ""}, and can no longer change it.</p>
          <span className="flex flex-wrap gap-2">
            <Button variant="danger" disabled={busy} onClick={() => onAction(fields, { do: "decline", note })}>
              Decline it
            </Button>
            <Button variant="ghost" onClick={() => setDeclining(false)}>
              Keep it
            </Button>
          </span>
        </div>
      )}

      {missing && <p className="text-sm text-blood-bright">{missing}</p>}
      <ErrorText error={error} />

      <div className="flex flex-wrap items-center gap-2">
        {!writes ? (
          <Button disabled={busy} onClick={() => act(post ? { do: "save" } : { do: "propose" })}>
            {post ? "Save the proposal" : "Send the proposal"}
          </Button>
        ) : published ? (
          <Button disabled={busy} onClick={() => act({ do: "save" })}>
            Save changes
          </Button>
        ) : (
          <>
            <Button disabled={busy} onClick={() => act({ do: "publish", note })}>
              Publish now
            </Button>
            {!scheduling && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  if (!when) setWhen(suggestedTime(new Date(), dates.toInput));
                  setScheduling(true);
                }}
              >
                Schedule…
              </Button>
            )}
            <Button variant="secondary" disabled={busy} onClick={() => act({ do: "draft" })}>
              {status === "scheduled" ? "Unschedule and keep as a draft" : proposal ? "Take it up as a draft" : "Save draft"}
            </Button>
            {proposal && (
              <Button variant="danger" disabled={busy} onClick={() => setDeclining(true)}>
                Decline…
              </Button>
            )}
          </>
        )}
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {!writes && <p className="text-xs text-mist">A storyteller or assistant storyteller publishes it, or declines it. You're told either way.</p>}
      {writes && published && post?.discord?.state !== "app_only" && <p className="text-xs text-mist">Saving changes it in the app at once, and on Discord within a minute.</p>}
    </div>
  );
}
