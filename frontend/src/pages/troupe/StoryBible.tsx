import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, StoryBibleNoteOut, StoryBibleOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Dialog } from "../../components/Dialog";
import { Markdown } from "../../components/Markdown";
import { Button, Card, ErrorText, Field, Input, Loading, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { typeText } from "./locations";
import { FORM_NAMES, type NpcForm } from "./npcKinds";
import { moved } from "./settingStyle";
import { LEFT } from "./sireLines";
import { chronology, type Entry } from "./storyBible";

/** The troupe's story bible, for its running staff only. */
export function useStoryBible(troupeId: string) {
  return useQuery({
    queryKey: ["story-bible", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/story-bible", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
}

/** The bible's colours: on the app's dark page, or black on white for print. */
const TONES = {
  page: { soft: "text-mist", head: "text-gold" },
  print: { soft: "text-neutral-700", head: "text-black font-semibold" },
};
type Tone = (typeof TONES)["page"];

/**
 * The story bible tab (#879): the staff-only companion to the Setting Style Document
 * (MET: VTM p. 336). Staff's own notes, then what Horatio already holds: the
 * chronicle as its chronology, the troupe's NPCs and its Stock Locations. Players
 * never see it.
 */
export function StoryBibleTab({ troupeId }: { troupeId: string }) {
  const bible = useStoryBible(troupeId);
  const base = `/troupes/${troupeId}`;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        For staff only: players never see it. Beside the{" "}
        <Link to={`${base}/setting`} className="underline hover:text-parchment">
          Setting
        </Link>{" "}
        players read, it keeps your own notes with the chronicle, the troupe's NPCs and its locations as Horatio already holds them.{" "}
        <Link to={`/print/story-bible/${troupeId}`} target="_blank" className="underline hover:text-parchment">
          Print it
        </Link>
      </p>
      {bible.isPending ? (
        <Loading />
      ) : bible.error ? (
        <ErrorText error={bible.error} />
      ) : (
        <>
          <Notes troupeId={troupeId} notes={bible.data.notes} />
          <Card>
            <StoryBibleParts bible={bible.data} troupeId={troupeId} />
          </Card>
        </>
      )}
    </div>
  );
}

/**
 * What the bible brings together from Horatio's records: the chronology, the
 * important NPCs and the recurring locales. With `print`, black on white with every
 * event shown and no links.
 */
export function StoryBibleParts({ bible, troupeId, print = false }: { bible: StoryBibleOut; troupeId: string; print?: boolean }) {
  const tone = print ? TONES.print : TONES.page;
  const base = `/troupes/${troupeId}`;
  const { dated, undated } = chronology(bible.chronology);
  const inPlay = bible.npcs.filter((n) => n.status !== "retired");
  const retired = bible.npcs.filter((n) => n.status === "retired");
  return (
    <div className="flex flex-col gap-6">
      <Part title="Chronology" tone={tone} more={!print && { to: `${base}/chronicle`, label: "See the timeline" }}>
        {dated.length === 0 ? <p className={`text-sm ${tone.soft}`}>Nothing has an in-game date yet.</p> : <Events entries={dated} tone={tone} />}
        {undated.length > 0 &&
          (print ? (
            <>
              <h4 className="mt-2 text-sm font-semibold">Without an in-game date</h4>
              <Events entries={undated} tone={tone} />
            </>
          ) : (
            <details className="text-sm">
              <summary className={`cursor-pointer ${tone.soft}`}>Without an in-game date ({undated.length}), as Horatio recorded them</summary>
              <div className="mt-2">
                <Events entries={undated} tone={tone} />
              </div>
            </details>
          ))}
      </Part>

      <Part
        title="Important NPCs"
        tone={tone}
        more={
          !print && {
            to: `${base}/characters?show=npcs`,
            label: "Keep them under Characters",
          }
        }
      >
        {bible.npcs.length === 0 ? (
          <p className={`text-sm ${tone.soft}`}>The troupe has no NPCs yet.</p>
        ) : (
          <>
            <Npcs npcs={inPlay} troupeId={troupeId} tone={tone} print={print} />
            {retired.length > 0 && (
              <>
                <h4 className={`mt-2 text-sm ${print ? "font-semibold" : tone.soft}`}>No longer in play</h4>
                <Npcs npcs={retired} troupeId={troupeId} tone={tone} print={print} />
              </>
            )}
          </>
        )}
      </Part>

      <Part
        title="Recurring locales"
        tone={tone}
        more={
          !print && {
            to: `${base}/locations`,
            label: "Keep them under Locations",
          }
        }
      >
        {bible.locales.length === 0 ? (
          <p className={`text-sm ${tone.soft}`}>The troupe has no locations yet.</p>
        ) : (
          <ul aria-label="Recurring locales" className="flex flex-col gap-3 text-sm">
            {bible.locales.map((l) => (
              <li key={l.id} className="break-inside-avoid">
                <p>
                  {print ? (
                    <span className="font-medium">{l.name}</span>
                  ) : (
                    <Link to={`${base}/locations/${l.id}`} className="font-medium hover:text-gold">
                      {l.name}
                    </Link>
                  )}
                  <span className={tone.soft}>
                    {" "}
                    · {typeText(l)}
                    {l.parent && ` · part of ${l.parent}`}
                    {` · ${l.controller ? `held by ${l.controller}` : "uncontrolled"}`}
                  </span>
                </p>
                {l.address && <p className={tone.soft}>{l.address}</p>}
                {l.description && <p className="whitespace-pre-line">{l.description}</p>}
                {l.notes && <p className={`whitespace-pre-line ${tone.soft}`}>Notes: {l.notes}</p>}
              </li>
            ))}
          </ul>
        )}
      </Part>
    </div>
  );
}

function Part({ title, tone, more, children }: { title: string; tone: Tone; more?: { to: string; label: string } | false; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className={`text-base ${tone.head}`}>{title}</h3>
        {more && (
          <Link to={more.to} className="text-xs text-mist underline hover:text-parchment">
            {more.label}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function Events({ entries, tone }: { entries: Entry[]; tone: Tone }) {
  return (
    <ol className="flex flex-col gap-1 text-sm">
      {entries.map(({ event: e, when }) => (
        <li key={e.key} className="grid gap-x-3 sm:grid-cols-[12rem_1fr]">
          <span className={tone.soft}>{when}</span>
          <span>
            {e.character_name}: {e.label}
            {e.detail && <span className={tone.soft}>. {e.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Npcs({ npcs, troupeId, tone, print }: { npcs: CharacterOut[]; troupeId: string; tone: Tone; print: boolean }) {
  const named = useClanName();
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {npcs.map((n) => {
        // A Stock NPC's builder stands in for a sheet (issue #215).
        const to = n.npc_form === "stock" ? `/troupes/${troupeId}/npcs/${n.id}` : `/characters/${n.id}`;
        const about = [
          n.npc_kind_name ?? n.splat,
          n.clan && named(n.clan),
          FORM_NAMES[(n.npc_form ?? "sheeted") as NpcForm],
          n.status === "retired" && ((n.left_reason && LEFT[n.left_reason]) || "Retired"),
        ].filter(Boolean);
        return (
          <li key={n.id}>
            {print ? (
              <span className="font-medium">{n.name}</span>
            ) : (
              <Link to={to} className="font-medium hover:text-gold">
                {n.name}
              </Link>
            )}
            <span className={tone.soft}> · {about.join(" · ")}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Staff's own notes, in order, each a title and Markdown. */
function Notes({ troupeId, notes }: { troupeId: string; notes: StoryBibleNoteOut[] }) {
  const [editing, setEditing] = useState<StoryBibleNoteOut | "new" | null>(null);
  const [removing, setRemoving] = useState<StoryBibleNoteOut | null>(null);
  const path = { troupe_id: troupeId };
  const order = useAction((ids: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/story-bible/order", {
        params: { path },
        body: { ids },
      }),
    ),
  );
  const remove = useAction(async (note: StoryBibleNoteOut) => {
    await unwrap(
      api.DELETE("/api/troupes/{troupe_id}/story-bible/notes/{note_id}", {
        params: { path: { ...path, note_id: note.id } },
      }),
    );
    setRemoving(null);
  });
  const ids = notes.map((n) => n.id);
  return (
    <Card
      title="Staff notes"
      actions={
        <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing("new")}>
          Add a note
        </Button>
      }
    >
      {notes.length === 0 ? (
        <p className="text-sm text-mist">No notes yet: plots, secrets, what the players don't know.</p>
      ) : (
        <ol aria-label="Staff notes" className="divide-y divide-ash">
          {notes.map((note, n) => (
            <li key={note.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2">
              <div className="flex min-w-40 flex-1 flex-col gap-1">
                <h3 className="font-medium">{note.title}</h3>
                {note.body && <Markdown text={note.body} />}
              </div>
              <span className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  className="min-h-8 px-2"
                  aria-label={`Move ${note.title} up`}
                  disabled={n === 0 || order.isPending}
                  onClick={() => order.mutate(moved(ids, note.id, n - 1))}
                >
                  ↑
                </Button>
                <Button
                  variant="ghost"
                  className="min-h-8 px-2"
                  aria-label={`Move ${note.title} down`}
                  disabled={n === notes.length - 1 || order.isPending}
                  onClick={() => order.mutate(moved(ids, note.id, n + 1))}
                >
                  ↓
                </Button>
                <Button variant="secondary" className="min-h-8 px-3" aria-label={`Edit ${note.title}`} onClick={() => setEditing(note)}>
                  Edit
                </Button>
                <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove ${note.title}`} onClick={() => setRemoving(note)}>
                  Remove
                </Button>
              </span>
            </li>
          ))}
        </ol>
      )}
      <ErrorText error={order.error} />
      <Dialog title={editing === "new" ? "Add a note" : "Edit the note"} open={editing !== null} onClose={() => setEditing(null)} wide phoneFull>
        {editing !== null && <NoteEditor troupeId={troupeId} note={editing === "new" ? null : editing} onDone={() => setEditing(null)} />}
      </Dialog>
      <Dialog title="Remove this note?" open={removing !== null} onClose={() => setRemoving(null)}>
        <p className="text-sm">It goes from the story bible for every member of staff.</p>
        <ErrorText error={remove.error} />
        <div className="mt-4 flex gap-2">
          <Button onClick={() => removing && remove.mutate(removing)} disabled={remove.isPending}>
            Remove it
          </Button>
          <Button variant="ghost" onClick={() => setRemoving(null)}>
            Keep it
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}

function NoteEditor({ troupeId, note, onDone }: { troupeId: string; note: StoryBibleNoteOut | null; onDone: () => void }) {
  const [title, setTitle] = useState(note?.title ?? "");
  const [body, setBody] = useState(note?.body ?? "");
  const path = { troupe_id: troupeId };
  const save = useAction(async () => {
    if (note) {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/story-bible/notes/{note_id}", {
          params: { path: { ...path, note_id: note.id } },
          body: { title, body },
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/story-bible/notes", {
          params: { path },
          body: { title, body },
        }),
      );
    }
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label="Title">
        <Input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="The note, in Markdown" hint="Only staff read it.">
        <Textarea rows={8} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {note ? "Save" : "Add it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
