import { useQuery } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SettingEntryOut, SettingOut, SettingPresetOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Markdown } from "../../components/Markdown";
import { Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { moved, type Kind } from "./settingStyle";

const NOUNS: Record<Kind, string> = {
  theme: "theme",
  mood: "mood",
  note: "note",
};

/**
 * The parts of the troupe's Setting Style Document its staff write (#770): the
 * chronicle's subtitle and teaser, its scope, and its themes, moods and storyteller
 * notes, each an entry of its own in the order staff put it. Players read all of it.
 * Its running staff, assistant storytellers too, write it.
 */
export function SettingStyle({ troupeId }: { troupeId: string }) {
  const setting = useQuery({
    queryKey: ["setting", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/setting", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
  if (setting.isPending) return <Loading />;
  if (setting.error) return <ErrorText error={setting.error} />;
  const s = setting.data;
  return (
    <>
      <TitleCard troupeId={troupeId} setting={s} />
      <ScopeCard troupeId={troupeId} setting={s} />
      <Entries troupeId={troupeId} kind="theme" title="Themes" entries={s.themes} canEdit={s.can_edit} />
      <Entries troupeId={troupeId} kind="mood" title="Moods" entries={s.moods} canEdit={s.can_edit} />
      <Notes troupeId={troupeId} entries={s.notes} canEdit={s.can_edit} />
    </>
  );
}

type Text = Pick<SettingOut, "subtitle" | "teaser" | "power" | "agency">;

/** Save some of the document's text, keeping the rest as it is. */
function useSaveText(troupeId: string, setting: SettingOut) {
  return useAction((change: Partial<Text>) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/setting", {
        params: { path: { troupe_id: troupeId } },
        body: {
          subtitle: setting.subtitle,
          teaser: setting.teaser,
          power: setting.power,
          agency: setting.agency,
          ...change,
        },
      }),
    ),
  );
}

/** The chronicle's name from the profile, its subtitle, and its in-world teaser. */
function TitleCard({ troupeId, setting }: { troupeId: string; setting: SettingOut }) {
  const [subtitle, setSubtitle] = useState(setting.subtitle);
  const [teaser, setTeaser] = useState(setting.teaser);
  const [preview, setPreview] = useState(false);
  const save = useSaveText(troupeId, setting);
  const name = setting.chronicle || "No chronicle name yet";
  if (!setting.can_edit) {
    return (
      <Card title="Title and teaser">
        <p className="text-parchment">{name}</p>
        {setting.subtitle && <p className="text-sm text-mist">{setting.subtitle}</p>}
        <div className="mt-3">{setting.teaser ? <Markdown text={setting.teaser} /> : <p className="text-sm text-mist">No teaser yet.</p>}</div>
      </Card>
    );
  }
  const changed = subtitle !== setting.subtitle || teaser !== setting.teaser;
  return (
    <Card title="Title and teaser">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ subtitle, teaser });
        }}
      >
        <p className="text-sm">
          <span className="text-mist">Chronicle: </span>
          {name}{" "}
          <Link to={`/troupes/${troupeId}`} className="text-xs text-mist underline hover:text-parchment">
            (from the profile)
          </Link>
        </p>
        <Field label="Subtitle" hint="Under the chronicle's name, such as A City Under Siege.">
          <Input maxLength={200} value={subtitle} onChange={(e) => setSubtitle(e.target.value)} />
        </Field>
        <div className="flex flex-col gap-1 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="text-mist">{preview ? "How players will read it" : "Teaser, in Markdown"}</span>
            <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => setPreview(!preview)}>
              {preview ? "Write" : "Preview"}
            </Button>
          </div>
          {preview ? (
            <div className="min-h-24 rounded-md border border-ash p-3">
              {teaser.trim() ? <Markdown text={teaser} /> : <span className="text-mist">Nothing written yet.</span>}
            </div>
          ) : (
            <Textarea aria-label="Teaser, in Markdown" rows={6} maxLength={20000} value={teaser} onChange={(e) => setTeaser(e.target.value)} />
          )}
          <span className="text-xs text-mist">The chronicle as its characters know it. The troupe's description stays the short blurb on the troupe list.</span>
        </div>
        <ErrorText error={save.error} />
        <div>
          <Button type="submit" disabled={!changed || save.isPending}>
            Save title and teaser
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** The scope (MET: VTM pp. 329–330): its locale, the profile's city, and the power and agency of its characters. */
function ScopeCard({ troupeId, setting }: { troupeId: string; setting: SettingOut }) {
  const [power, setPower] = useState(setting.power);
  const [agency, setAgency] = useState(setting.agency);
  const save = useSaveText(troupeId, setting);
  const locale = setting.locale || "Not set";
  if (!setting.can_edit) {
    return (
      <Card title="Scope">
        <dl className="flex flex-col gap-2 text-sm">
          <ScopeEntry label="Locale">{locale}</ScopeEntry>
          <ScopeEntry label="Power">{setting.power || "Not set"}</ScopeEntry>
          <ScopeEntry label="Agency">{setting.agency || "Not set"}</ScopeEntry>
        </dl>
      </Card>
    );
  }
  const changed = power !== setting.power || agency !== setting.agency;
  return (
    <Card title="Scope">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ power, agency });
        }}
      >
        <p className="text-sm">
          <span className="text-mist">Locale: </span>
          {locale}{" "}
          <Link to={`/troupes/${troupeId}`} className="text-xs text-mist underline hover:text-parchment">
            (the profile's city)
          </Link>
        </p>
        <Field label="Power" hint="How powerful characters are, such as neonates and ancillae only.">
          <Textarea rows={2} maxLength={2000} value={power} onChange={(e) => setPower(e.target.value)} />
        </Field>
        <Field label="Agency" hint="How far characters can change the story, such as nothing beyond the city.">
          <Textarea rows={2} maxLength={2000} value={agency} onChange={(e) => setAgency(e.target.value)} />
        </Field>
        <ErrorText error={save.error} />
        <div>
          <Button type="submit" disabled={!changed || save.isPending}>
            Save scope
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ScopeEntry({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <dt className="text-mist">{label}</dt>
      <dd className="whitespace-pre-line">{children}</dd>
    </div>
  );
}

/** Put a kind's entries in a new order, by dragging or by the move buttons. */
function useOrder(troupeId: string, kind: Kind) {
  return useAction((ids: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/setting/order", {
        params: { path: { troupe_id: troupeId } },
        body: { kind, ids },
      }),
    ),
  );
}

/** Dragging one entry onto another puts it in that one's place. */
function useDrag(entries: SettingEntryOut[], reorder: (ids: string[]) => void, enabled: boolean) {
  const [dragging, setDragging] = useState<string | null>(null);
  return (entry: SettingEntryOut) =>
    enabled
      ? {
          draggable: true,
          onDragStart: (e: DragEvent) => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", entry.id);
            setDragging(entry.id);
          },
          onDragOver: (e: DragEvent) => {
            if (dragging && dragging !== entry.id) e.preventDefault();
          },
          onDrop: (e: DragEvent) => {
            e.preventDefault();
            const from = dragging ?? e.dataTransfer.getData("text/plain");
            setDragging(null);
            const ids = entries.map((x) => x.id);
            const to = ids.indexOf(entry.id);
            if (from && from !== entry.id) reorder(moved(ids, from, to));
          },
          onDragEnd: () => setDragging(null),
        }
      : {};
}

/** Themes or moods: chips in order, each opening to its description. */
function Entries({
  troupeId,
  kind,
  title,
  entries,
  canEdit,
}: {
  troupeId: string;
  kind: "theme" | "mood";
  title: string;
  entries: SettingEntryOut[];
  canEdit: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<SettingEntryOut | "new" | null>(null);
  const [removing, setRemoving] = useState<SettingEntryOut | null>(null);
  const order = useOrder(troupeId, kind);
  const drag = useDrag(entries, (ids) => order.mutate(ids), canEdit && !order.isPending);
  const shown = entries.find((e) => e.id === open);
  const at = shown ? entries.indexOf(shown) : -1;
  const ids = entries.map((e) => e.id);
  return (
    <Card
      title={title}
      actions={
        canEdit && (
          <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing("new")}>
            Add a {kind}
          </Button>
        )
      }
    >
      {entries.length === 0 ? (
        <p className="text-sm text-mist">No {kind}s yet.</p>
      ) : (
        <ul aria-label={title} className="flex flex-wrap gap-2">
          {entries.map((e) => (
            <li key={e.id} {...drag(e)} className={canEdit ? "cursor-grab" : undefined}>
              <button
                type="button"
                aria-expanded={open === e.id}
                onClick={() => setOpen(open === e.id ? null : e.id)}
                className={`min-h-8 rounded-full border px-3 text-sm ${open === e.id ? "border-gold text-gold" : "border-ash text-parchment hover:border-mist"}`}
              >
                {e.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {canEdit && entries.length > 1 && <p className="mt-2 text-xs text-mist">Drag a {kind} onto another to put it in that place.</p>}
      {shown && (
        <div className="mt-3 rounded-md border border-ash p-3" aria-label={shown.name} role="region">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-gold">{shown.name}</span>
            {shown.page && <span className="text-xs text-mist">From the book's sample, MET: VTM p. {shown.page}</span>}
          </div>
          {shown.description ? <Markdown text={shown.description} /> : <p className="text-sm text-mist">No description.</p>}
          {canEdit && (
            <div className="mt-3 flex flex-wrap gap-1">
              <Button
                variant="ghost"
                className="min-h-8 px-2"
                aria-label={`Move ${shown.name} earlier`}
                disabled={at === 0 || order.isPending}
                onClick={() => order.mutate(moved(ids, shown.id, at - 1))}
              >
                ← Earlier
              </Button>
              <Button
                variant="ghost"
                className="min-h-8 px-2"
                aria-label={`Move ${shown.name} later`}
                disabled={at === entries.length - 1 || order.isPending}
                onClick={() => order.mutate(moved(ids, shown.id, at + 1))}
              >
                Later →
              </Button>
              <Button variant="secondary" className="min-h-8 px-3" aria-label={`Edit ${shown.name}`} onClick={() => setEditing(shown)}>
                Edit
              </Button>
              <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove ${shown.name}`} onClick={() => setRemoving(shown)}>
                Remove
              </Button>
            </div>
          )}
        </div>
      )}
      <ErrorText error={order.error} />
      <Dialog
        title={editing === "new" ? `Add a ${kind}` : `Edit ${editing?.name ?? ""}`}
        open={editing !== null}
        onClose={() => setEditing(null)}
        wide
        phoneFull
      >
        {editing !== null && (
          <EntryEditor troupeId={troupeId} kind={kind} entry={editing === "new" ? null : editing} taken={entries} onDone={() => setEditing(null)} />
        )}
      </Dialog>
      <Remove troupeId={troupeId} entry={removing} what={removing?.name ?? ""} onDone={() => setRemoving(null)} />
    </Card>
  );
}

/** The storyteller notes, in order, each a line or more of Markdown. */
function Notes({ troupeId, entries, canEdit }: { troupeId: string; entries: SettingEntryOut[]; canEdit: boolean }) {
  const [editing, setEditing] = useState<SettingEntryOut | "new" | null>(null);
  const [removing, setRemoving] = useState<SettingEntryOut | null>(null);
  const order = useOrder(troupeId, "note");
  const drag = useDrag(entries, (ids) => order.mutate(ids), canEdit && !order.isPending);
  const ids = entries.map((e) => e.id);
  return (
    <Card
      title="Storyteller notes"
      actions={
        canEdit && (
          <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing("new")}>
            Add a note
          </Button>
        )
      }
    >
      {entries.length === 0 ? (
        <p className="text-sm text-mist">No notes yet.</p>
      ) : (
        <ol aria-label="Storyteller notes" className="divide-y divide-ash">
          {entries.map((e, n) => (
            <li key={e.id} {...drag(e)} className={`flex flex-wrap items-start gap-x-3 gap-y-1 py-2 ${canEdit ? "cursor-grab" : ""}`}>
              <div className="min-w-40 flex-1">
                <Markdown text={e.description} />
              </div>
              {canEdit && (
                <span className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    className="min-h-8 px-2"
                    aria-label={`Move note ${n + 1} up`}
                    disabled={n === 0 || order.isPending}
                    onClick={() => order.mutate(moved(ids, e.id, n - 1))}
                  >
                    ↑
                  </Button>
                  <Button
                    variant="ghost"
                    className="min-h-8 px-2"
                    aria-label={`Move note ${n + 1} down`}
                    disabled={n === entries.length - 1 || order.isPending}
                    onClick={() => order.mutate(moved(ids, e.id, n + 1))}
                  >
                    ↓
                  </Button>
                  <Button variant="secondary" className="min-h-8 px-3" aria-label={`Edit note ${n + 1}`} onClick={() => setEditing(e)}>
                    Edit
                  </Button>
                  <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove note ${n + 1}`} onClick={() => setRemoving(e)}>
                    Remove
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      <ErrorText error={order.error} />
      <Dialog title={editing === "new" ? "Add a note" : "Edit the note"} open={editing !== null} onClose={() => setEditing(null)} wide phoneFull>
        {editing !== null && (
          <EntryEditor troupeId={troupeId} kind="note" entry={editing === "new" ? null : editing} taken={entries} onDone={() => setEditing(null)} />
        )}
      </Dialog>
      <Remove troupeId={troupeId} entry={removing} what="this note" onDone={() => setRemoving(null)} />
    </Card>
  );
}

/** Add an entry, from one of the book's samples or of the troupe's own, or change one. */
function EntryEditor({
  troupeId,
  kind,
  entry,
  taken,
  onDone,
}: {
  troupeId: string;
  kind: Kind;
  entry: SettingEntryOut | null;
  taken: SettingEntryOut[];
  onDone: () => void;
}) {
  const [name, setName] = useState(entry?.name ?? "");
  const [description, setDescription] = useState(entry?.description ?? "");
  const [bookKey, setBookKey] = useState("");
  const presets = useQuery({
    queryKey: ["setting-presets"],
    queryFn: () => unwrap(api.GET("/api/setting-presets")),
    staleTime: Infinity,
    enabled: !entry && kind !== "note",
  });
  const used = new Set(taken.map((e) => e.book_key));
  const offered = (presets.data ?? []).filter((p) => p.kind === kind && !used.has(p.key));
  const pick = (key: string) => {
    setBookKey(key);
    const found: SettingPresetOut | undefined = offered.find((p) => p.key === key);
    setName(found?.name ?? "");
    setDescription(found?.description ?? "");
  };
  const path = { troupe_id: troupeId };
  const save = useAction(async () => {
    if (entry) {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/setting/entries/{entry_id}", {
          params: { path: { ...path, entry_id: entry.id } },
          body: { name, description },
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/setting/entries", {
          params: { path },
          body: { kind, name, description, book_key: bookKey || null },
        }),
      );
    }
    onDone();
  });
  const label = kind === "note" ? "The note, in Markdown" : "Description, in Markdown";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {!entry && kind !== "note" && (
        <Field label="Start from" hint="One of the book's samples fills in its name and description, for you to change as you like.">
          <Select value={bookKey} onChange={(e) => pick(e.target.value)}>
            <option value="">A {NOUNS[kind]} of your own</option>
            {offered.map((p) => (
              <option key={p.key} value={p.key}>
                {p.name} (p. {p.page})
              </option>
            ))}
          </Select>
        </Field>
      )}
      {kind !== "note" && (
        <Field label="Name">
          <Input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
      )}
      <Field
        label={label}
        hint={
          kind === "theme"
            ? "The questions it asks."
            : kind === "mood"
              ? "How the chronicle feels."
              : "Such as: characters are no older than ten years past the Embrace."
        }
      >
        <Textarea
          required={kind === "note"}
          rows={kind === "note" ? 3 : 5}
          maxLength={20000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <ErrorText error={save.error ?? presets.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {entry ? "Save" : "Add it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Remove({ troupeId, entry, what, onDone }: { troupeId: string; entry: SettingEntryOut | null; what: string; onDone: () => void }) {
  const remove = useAction(async (e: SettingEntryOut) => {
    await unwrap(
      api.DELETE("/api/troupes/{troupe_id}/setting/entries/{entry_id}", {
        params: { path: { troupe_id: troupeId, entry_id: e.id } },
      }),
    );
    onDone();
  });
  return (
    <Dialog title={`Remove ${what}?`} open={entry !== null} onClose={onDone}>
      <p className="text-sm">Players will no longer read it.</p>
      <ErrorText error={remove.error} />
      <div className="mt-4 flex gap-2">
        <Button onClick={() => entry && remove.mutate(entry)} disabled={remove.isPending}>
          Remove it
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Keep it
        </Button>
      </div>
    </Dialog>
  );
}
