import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SharedBackgroundOut, SharedChoicesOut, SharedEntryOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { actionText, dotsText, entryText, sharersText, totalText } from "./sharedBackgrounds";

/** Said wherever a shared background is shown: nothing here touches a sheet. */
export const RECORD_ONLY = "A record only: nothing logged here changes a rating on anyone's sheet.";

/**
 * One shared background: who has dots in it, what it gives, and its log of dots
 * put in and taken out and of uses, newest first. Staff log anything and change
 * it; a player logs uses for their own characters.
 */
export function SharedBackgroundView({ shared, onDeleted }: { shared: SharedBackgroundOut; onDeleted?: () => void }) {
  const [open, setOpen] = useState<"use" | "dots" | "edit" | null>(null);
  const choices = useQuery({
    queryKey: ["shared-choices", shared.troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/shared-backgrounds/choices", { params: { path: { troupe_id: shared.troupe_id } } })),
    enabled: shared.can_manage,
  });
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/shared-backgrounds/{shared_id}", { params: { path: { shared_id: shared.id } } }));
    onDeleted?.();
  });
  const unlog = useAction((id: string) => unwrap(api.DELETE("/api/shared-background-entries/{entry_id}", { params: { path: { entry_id: id } } })));
  const users = shared.sharers.filter((s) => s.can_log_use);
  const done = () => setOpen(null);

  return (
    <Card
      title={shared.name}
      actions={
        <div className="flex flex-wrap gap-2">
          {users.length > 0 && open !== "use" && (
            <Button variant="secondary" onClick={() => setOpen("use")}>
              Log a use
            </Button>
          )}
          {shared.can_manage && open !== "dots" && (
            <Button variant="secondary" onClick={() => setOpen("dots")}>
              Log dots
            </Button>
          )}
          {shared.can_manage && open !== "edit" && (
            <Button variant="ghost" onClick={() => setOpen("edit")}>
              Edit
            </Button>
          )}
          {shared.can_manage && (
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(`Delete ${shared.name} and its whole log?`)) remove.mutate(undefined);
              }}
            >
              Delete
            </Button>
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        <p>
          <strong className="text-gold">{shared.background}</strong> · {totalText(shared)}
          {shared.can_manage || <span className="text-mist"> · {shared.troupe_name}</span>}
        </p>
        <p aria-label="Sharing it">{sharersText(shared.sharers)}</p>
        {shared.notes && (
          <p>
            <span className="text-mist">What it gives: </span>
            {shared.notes}
          </p>
        )}
        <p className="text-xs text-mist">{RECORD_ONLY}</p>
        {open === "use" && <UseForm shared={shared} onDone={done} />}
        {open === "dots" && (choices.data ? <DotsForm shared={shared} choices={choices.data} onDone={done} /> : <ErrorText error={choices.error} />)}
        {open === "edit" && (choices.data ? <EditForm shared={shared} choices={choices.data} onDone={done} /> : <ErrorText error={choices.error} />)}
        <ErrorText error={remove.error ?? unlog.error} />
        <h3 className="mt-2 text-base text-gold">Log</h3>
        {shared.entries.length === 0 ? (
          <Empty>Nothing logged yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-2" aria-label={`${shared.name} log`}>
            {shared.entries.map((e) => (
              <EntryRow
                key={e.id}
                entry={e}
                onDelete={() => {
                  if (window.confirm(`Take “${entryText(e)}” off the log?`)) unlog.mutate(e.id);
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function EntryRow({ entry, onDelete }: { entry: SharedEntryOut; onDelete: () => void }) {
  const dates = useDates();
  return (
    <li className="flex flex-col gap-1 rounded-md border border-ash bg-night/40 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <time dateTime={entry.happened_at}>{dates.dateTime(entry.happened_at)}</time>
        <span>·</span>
        {entry.character_id ? (
          <Link to={`/characters/${entry.character_id}`} className="hover:text-gold">
            {entry.name}
          </Link>
        ) : (
          <span>{entry.name}</span>
        )}
        <span className={entry.kind === "use" ? "" : "text-gold"}> {actionText(entry)}</span>
      </div>
      {entry.purpose && <p>{entry.purpose}</p>}
      {entry.note && <p className="text-mist">{entry.note}</p>}
      <div className="flex flex-wrap items-center gap-2 text-xs text-mist">
        {entry.kind === "use" ? <Badge>Use</Badge> : <Badge tone="gold">{entry.kind === "contribution" ? "Dots in" : "Dots out"}</Badge>}
        {entry.logged_by_name && (
          <span>
            logged by {entry.logged_by_name}, {dates.date(entry.logged_at)}
          </span>
        )}
        {entry.can_delete && (
          <Button variant="ghost" className="ml-auto min-h-0 px-2 py-0" onClick={onDelete}>
            Delete
          </Button>
        )}
      </div>
    </li>
  );
}

/* A time left as the form opened with goes as none, and the server dates the entry
 * to the second, so it sorts after what was logged just before it. */
function UseForm({ shared, onDone }: { shared: SharedBackgroundOut; onDone: () => void }) {
  const dates = useDates();
  const users = shared.sharers.filter((s) => s.can_log_use);
  const [who, setWho] = useState(users[0]?.character_id ?? "");
  const [now] = useState(() => dates.toInput(new Date()));
  const [when, setWhen] = useState(now);
  const [purpose, setPurpose] = useState("");
  const [note, setNote] = useState("");
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/shared-backgrounds/{shared_id}/entries", {
        params: { path: { shared_id: shared.id } },
        body: { kind: "use", character_id: who, happened_at: when === now ? undefined : dates.fromInput(when).toISOString(), purpose, note },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Log a use"
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Who drew on it">
          <Select value={who} onChange={(e) => setWho(e.target.value)}>
            {users.map((s) => (
              <option key={s.character_id} value={s.character_id ?? ""}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={`When (${dates.zoneName()})`}>
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
      </div>
      <Field label="What for">
        <Input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Hiding from the hunters for the day" />
      </Field>
      <Field label="Note (optional)">
        <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !who || !when}>
          Log use
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DotsForm({ shared, choices, onDone }: { shared: SharedBackgroundOut; choices: SharedChoicesOut; onDone: () => void }) {
  const dates = useDates();
  const [kind, setKind] = useState<"contribution" | "withdrawal">("contribution");
  const [who, setWho] = useState("");
  const [dots, setDots] = useState(1);
  const [now] = useState(() => dates.toInput(new Date()));
  const [when, setWhen] = useState(now);
  const [note, setNote] = useState("");
  // Dots go in from anyone in the troupe, and come out only from who has some in.
  const people =
    kind === "contribution"
      ? choices.characters.map((c) => ({ id: c.id, name: c.name }))
      : shared.sharers.filter((s) => s.dots > 0 && s.character_id).map((s) => ({ id: s.character_id!, name: `${s.name} (${dotsText(s.dots)})` }));
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/shared-backgrounds/{shared_id}/entries", {
        params: { path: { shared_id: shared.id } },
        body: { kind, character_id: who, dots, happened_at: when === now ? undefined : dates.fromInput(when).toISOString(), purpose: "", note },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Log dots"
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Dots">
          <Select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as typeof kind);
              setWho("");
            }}
          >
            <option value="contribution">Put in</option>
            <option value="withdrawal">Taken out</option>
          </Select>
        </Field>
        <Field label="Who">
          <Select value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Choose…</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="How many">
          <Input type="number" min={1} max={10} value={dots} onChange={(e) => setDots(Number(e.target.value))} />
        </Field>
        <Field label={`When (${dates.zoneName()})`}>
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
      </div>
      <Field label="Note (optional)">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={kind === "withdrawal" ? "Left the coterie" : "Bought with XP"} />
      </Field>
      {kind === "withdrawal" && (
        <p className="text-xs text-mist">
          When a sharer dies or leaves the group, their dots are lost after 30 days or two games, whichever is longer, unless the others buy them again ({choices.page}).
        </p>
      )}
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !who || dots < 1 || !when}>
          Log dots
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function EditForm({ shared, choices, onDone }: { shared: SharedBackgroundOut; choices: SharedChoicesOut; onDone: () => void }) {
  const [name, setName] = useState(shared.name);
  const [background, setBackground] = useState(shared.background);
  const [notes, setNotes] = useState(shared.notes);
  const save = useAction(async () => {
    await unwrap(api.PATCH("/api/shared-backgrounds/{shared_id}", { params: { path: { shared_id: shared.id } }, body: { name, background, notes } }));
    onDone();
  });
  return (
    <form
      aria-label="Edit the shared background"
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Background">
          <Select value={background} onChange={(e) => setBackground(e.target.value)}>
            {[...new Set([shared.background, ...choices.backgrounds])].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="What it gives (optional)">
        <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !name.trim()}>
          Save changes
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** A character's shared backgrounds, on its page: for its player, mostly. */
export function CharacterShared({ characterId }: { characterId: string }) {
  const shared = useQuery({
    queryKey: ["character-shared", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/shared-backgrounds", { params: { path: { character_id: characterId } } })),
  });
  if (shared.isPending) return <Loading />;
  if (shared.error) return <ErrorText error={shared.error} />;
  if (shared.data.length === 0) return <Empty>This character shares no backgrounds.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      {shared.data.map((s) => (
        <SharedBackgroundView key={s.id} shared={s} />
      ))}
    </div>
  );
}
