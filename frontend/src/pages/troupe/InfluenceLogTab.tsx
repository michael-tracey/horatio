import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { InfluenceChoicesOut, InfluenceEntryIn, InfluenceEntryOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { TYPE_NAMES } from "../../influence";
import { BlockSources } from "./BlockSources";
import { logQuery, NO_FILTERS, sourceText, whoText, type LogFilters } from "./influenceLog";

const PAGE = 100;

/** Every influence action taken in the troupe, for its storytellers and assistants. Players never see it. */
export function InfluenceLogTab({ troupeId }: { troupeId: string }) {
  const dates = useDates();
  const [filters, setFilters] = useState<LogFilters>(NO_FILTERS);
  const [limit, setLimit] = useState(PAGE);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const path = { troupe_id: troupeId };
  const choices = useQuery({
    queryKey: ["influence-choices", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-log/choices", { params: { path } })),
  });
  const query = { ...logQuery(filters, dates), limit };
  const log = useQuery({
    queryKey: ["influence-log", troupeId, query],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-log", { params: { path, query } })),
  });
  const merge = useAction(async (ids: string[]) => {
    const [keep, ...others] = ids;
    await unwrap(api.POST("/api/influence-entries/{entry_id}/merge", { params: { path: { entry_id: keep! } }, body: { entry_ids: others } }));
    setSelected([]);
  });
  const remove = useAction((id: string) => unwrap(api.DELETE("/api/influence-entries/{entry_id}", { params: { path: { entry_id: id } } })));

  if (choices.isPending) return <Loading />;
  if (choices.error) return <ErrorText error={choices.error} />;
  const set = (change: Partial<LogFilters>) => {
    setFilters({ ...filters, ...change });
    setLimit(PAGE);
  };
  const types = choices.data.types.filter((t) => !filters.type || t.type === filters.type);
  const actions = [...new Map(types.flatMap((t) => t.actions).map((a) => [a.key, a])).values()];
  const specializations = [...new Set(types.flatMap((t) => t.specializations))].sort();
  // Merge into the oldest selected: the list is newest first.
  const toMerge = (log.data?.entries ?? []).filter((e) => selected.includes(e.id)).reverse();

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Influence log"
        actions={
          !adding && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Log influence
            </Button>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">Every influence action taken in this troupe. Players never see this log, only their own characters' actions.</p>
        {adding && <EntryForm troupeId={troupeId} choices={choices.data} onDone={() => setAdding(false)} />}
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Field label="Type">
            <Select value={filters.type} onChange={(e) => set({ type: e.target.value as LogFilters["type"], action: "" })}>
              <option value="">Both</option>
              <option value="elite">Elite</option>
              <option value="underworld">Underworld</option>
            </Select>
          </Field>
          <Field label="Specialisation">
            <Select value={filters.specialization} onChange={(e) => set({ specialization: e.target.value })}>
              <option value="">Any</option>
              {specializations.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
          </Field>
          <Field label="Character">
            <Select value={filters.who} onChange={(e) => set({ who: e.target.value })}>
              <option value="">Anyone</option>
              {choices.data.characters.map((c) => (
                <option key={c.id} value={`c:${c.id}`}>
                  {c.name}
                  {c.in_troupe ? "" : " (left the troupe)"}
                </option>
              ))}
              {choices.data.names.map((n) => (
                <option key={n} value={`n:${n}`}>
                  {n} (not in Horatio)
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Action">
            <Select value={filters.action} onChange={(e) => set({ action: e.target.value })}>
              <option value="">Any</option>
              {actions.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="From">
            <Input type="date" value={filters.from} onChange={(e) => set({ from: e.target.value })} />
          </Field>
          <Field label="To">
            <Input type="date" value={filters.to} onChange={(e) => set({ to: e.target.value })} />
          </Field>
        </div>
      </Card>
      {toMerge.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => merge.mutate(toMerge.map((e) => e.id))} disabled={merge.isPending}>
            Merge {toMerge.length} into {toMerge[0]!.short_id}
          </Button>
          <Button variant="ghost" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      )}
      <ErrorText error={merge.error ?? remove.error} />
      {log.isPending ? (
        <Loading />
      ) : log.error ? (
        <ErrorText error={log.error} />
      ) : log.data.entries.length === 0 ? (
        <Empty>No influence actions{filters === NO_FILTERS ? " logged yet" : " match these filters"}.</Empty>
      ) : (
        <>
          <p className="text-sm text-mist">
            {log.data.total} {log.data.total === 1 ? "entry" : "entries"}, newest first.
          </p>
          <ul className="flex flex-col gap-3">
            {log.data.entries.map((entry) =>
              editing === entry.id ? (
                <li key={entry.id}>
                  <Card title={`Edit ${entry.short_id}`}>
                    <EntryForm troupeId={troupeId} choices={choices.data} entry={entry} onDone={() => setEditing(null)} />
                  </Card>
                </li>
              ) : (
                <EntryRow
                  key={entry.id}
                  entry={entry}
                  selected={selected.includes(entry.id)}
                  onSelect={(on) => setSelected(on ? [...selected, entry.id] : selected.filter((i) => i !== entry.id))}
                  onEdit={() => setEditing(entry.id)}
                  onDelete={() => {
                    if (window.confirm(`Delete ${entry.short_id} from the influence log?`)) remove.mutate(entry.id);
                  }}
                />
              ),
            )}
          </ul>
          {log.data.total > log.data.entries.length && (
            <Button variant="secondary" className="self-start" onClick={() => setLimit(limit + PAGE)}>
              Show more
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function EntryRow({
  entry,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: {
  entry: InfluenceEntryOut;
  selected: boolean;
  onSelect: (on: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const dates = useDates();
  return (
    <li className="flex flex-col gap-2 rounded-md border border-ash bg-dusk p-3 text-sm" aria-label={`Entry ${entry.short_id}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <input type="checkbox" aria-label={`Select ${entry.short_id}`} checked={selected} onChange={(e) => onSelect(e.target.checked)} />
        <strong className="text-gold">{entry.short_id}</strong>
        <time dateTime={entry.happened_at}>{dates.dateTime(entry.happened_at)}</time>
        <span>·</span>
        {entry.character_id ? (
          <Link to={`/characters/${entry.character_id}`} className="hover:text-gold">
            {whoText(entry)}
          </Link>
        ) : (
          <span>{whoText(entry)}</span>
        )}
        <span className="text-mist">
          · {TYPE_NAMES[entry.type]}
          {entry.specialization && `, ${entry.specialization}`} · {entry.action}
        </span>
      </div>
      {entry.purpose && <p>{entry.purpose}</p>}
      <BlockSources entry={entry} />
      <div className="flex flex-wrap items-center gap-2 text-xs text-mist">
        {entry.times > 1 && <Badge tone="gold">logged {entry.times} times</Badge>}
        {entry.blocks > 0 && <Badge>{entry.blocks === 1 ? "1 block" : `${entry.blocks} blocks`}</Badge>}
        {entry.needs_details && <Badge tone="blood">needs details</Badge>}
        {entry.cycle_id && entry.source === "downtime" ? (
          <Link to={`/cycles/${entry.cycle_id}`} className="hover:text-gold">
            {sourceText(entry)}
          </Link>
        ) : (
          <span>{sourceText(entry)}</span>
        )}
        {entry.logged_by_name && <span>· logged by {entry.logged_by_name}</span>}
        <span className="ml-auto flex gap-2">
          <Button variant="ghost" className="px-2 py-0" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" className="px-2 py-0" onClick={onDelete}>
            Delete
          </Button>
        </span>
      </div>
    </li>
  );
}

/** Add an entry by hand, or change one. */
function EntryForm({
  troupeId,
  choices,
  entry,
  onDone,
}: {
  troupeId: string;
  choices: InfluenceChoicesOut;
  entry?: InfluenceEntryOut;
  onDone: () => void;
}) {
  const dates = useDates();
  const [form, setForm] = useState({
    type: entry?.type ?? "elite",
    who: entry ? (entry.character_id ? `c:${entry.character_id}` : "name") : "",
    name: entry && !entry.character_id ? entry.name : "",
    specialization: entry?.specialization ?? "",
    action_key: entry?.action_key ?? "",
    purpose: entry?.purpose ?? "",
    times: entry?.times ?? 1,
    blocks: entry?.blocks ?? 0,
    happened_at: dates.toInput(entry?.happened_at ?? new Date()),
    cycle_id: entry?.cycle_id ?? "",
    needs_details: entry?.needs_details ?? false,
  });
  const set = (change: Partial<typeof form>) => setForm({ ...form, ...change });
  const type = choices.types.find((t) => t.type === form.type)!;
  const save = useAction(async () => {
    const body: InfluenceEntryIn = {
      type: form.type,
      happened_at: dates.fromInput(form.happened_at).toISOString(),
      character_id: form.who.startsWith("c:") ? form.who.slice(2) : null,
      name: form.who === "name" ? form.name : "",
      specialization: form.specialization,
      action_key: form.action_key || null,
      purpose: form.purpose,
      times: form.times,
      blocks: form.blocks,
      cycle_id: form.cycle_id || null,
      needs_details: form.needs_details,
    };
    if (entry) await unwrap(api.PUT("/api/influence-entries/{entry_id}", { params: { path: { entry_id: entry.id } }, body }));
    else await unwrap(api.POST("/api/troupes/{troupe_id}/influence-log", { params: { path: { troupe_id: troupeId } }, body }));
    onDone();
  });
  // A character who has left can stay on an entry that already names them, but not be newly logged.
  const characters = choices.characters.filter((c) => c.in_troupe || `c:${c.id}` === form.who);

  return (
    <form
      aria-label={entry ? `Edit ${entry.short_id}` : "Log influence"}
      className="mb-4 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Who">
          <Select value={form.who} onChange={(e) => set({ who: e.target.value })}>
            <option value="">Choose…</option>
            {characters.map((c) => (
              <option key={c.id} value={`c:${c.id}`}>
                {c.name}
                {c.kind === "npc" ? " (NPC)" : ""}
                {c.in_troupe ? "" : " (left the troupe)"}
              </option>
            ))}
            <option value="name">Someone not in Horatio…</option>
          </Select>
        </Field>
        {form.who === "name" && (
          <Field label="Their name">
            <Input value={form.name} onChange={(e) => set({ name: e.target.value })} />
          </Field>
        )}
        <Field label="Type">
          <Select value={form.type} onChange={(e) => set({ type: e.target.value as typeof form.type, action_key: "" })}>
            {choices.types.map((t) => (
              <option key={t.type} value={t.type}>
                {t.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Specialisation">
          <Select value={form.specialization} onChange={(e) => set({ specialization: e.target.value })}>
            <option value="">None</option>
            {type.specializations.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <Field label="Action">
          <Select value={form.action_key} onChange={(e) => set({ action_key: e.target.value })}>
            <option value="">Choose…</option>
            {type.actions.map((a) => (
              <option key={a.key} value={a.key}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={`When (${dates.zoneName()})`}>
          <Input type="datetime-local" value={form.happened_at} onChange={(e) => set({ happened_at: e.target.value })} />
        </Field>
        <Field label="Downtime it applies to">
          <Select value={form.cycle_id} onChange={(e) => set({ cycle_id: e.target.value })}>
            <option value="">None</option>
            {choices.cycles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Times taken">
          <Input type="number" min={1} value={form.times} onChange={(e) => set({ times: Number(e.target.value) })} />
        </Field>
        <Field label="Blocks">
          <Input type="number" min={0} value={form.blocks} onChange={(e) => set({ blocks: Number(e.target.value) })} />
        </Field>
      </div>
      <Field label="Purpose">
        <Input value={form.purpose} onChange={(e) => set({ purpose: e.target.value })} placeholder="To smooth over the confession of the Dark Horse Hacker" />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.needs_details} onChange={(e) => set({ needs_details: e.target.checked })} />
        Needs details
      </label>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending || !form.who}>
          {entry ? "Save changes" : "Log it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
