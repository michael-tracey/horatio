import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { InfluenceChoicesOut, InfluenceEntryIn, InfluenceEntryOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, PageTabs, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { TYPE_NAMES } from "../../influence";
import { BlockSources } from "./BlockSources";
import { EffectsCard, ResolveButton, TargetFields, targetBody, targetForm } from "./InfluenceEffects";
import { logQuery, NO_FILTERS, sourceText, whoText, type LogFilters } from "./influenceLog";
import { allowanceWarning, another, cycleDate, specializationGroups, type EntryFields } from "./logInfluence";
import { WhoPicker } from "./WhoPicker";

const PAGE = 100;

/**
 * Every influence action taken in the troupe, for its storytellers and
 * assistants, and the effects targeted actions have made. Players never see it.
 */
export function InfluenceLogTab({ troupeId }: { troupeId: string }) {
  const base = `/troupes/${troupeId}/influence`;
  return (
    <>
      <PageTabs
        label="Influence log"
        tabs={[
          { to: base, label: "Log", end: true },
          { to: `${base}/effects`, label: "Effects and blocks" },
        ]}
      />
      <Routes>
        <Route index element={<Log troupeId={troupeId} />} />
        <Route path="effects" element={<EffectsCard troupeId={troupeId} />} />
      </Routes>
    </>
  );
}

function Log({ troupeId }: { troupeId: string }) {
  const dates = useDates();
  // ?needs=details, from the Waiting on you box, starts with only those.
  const [params] = useSearchParams();
  const [filters, setFilters] = useState<LogFilters>(() => (params.get("needs") === "details" ? { ...NO_FILTERS, needsDetails: true } : NO_FILTERS));
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
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={filters.needsDetails} onChange={(e) => set({ needsDetails: e.target.checked })} />
          Only those that need details
        </label>
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
          {entry.target?.text && ` → ${entry.target.text}`}
        </span>
      </div>
      {entry.purpose && <p>{entry.purpose}</p>}
      <BlockSources entry={entry} />
      <div className="flex flex-wrap items-center gap-2 text-xs text-mist">
        {entry.times > 1 && <Badge tone="gold">logged {entry.times} times</Badge>}
        {entry.blocks > 0 && <Badge>{entry.blocks === 1 ? "1 block" : `${entry.blocks} blocks`}</Badge>}
        {entry.needs_details && <Badge tone="blood">needs details</Badge>}
        {entry.effect && <Badge tone={entry.effect.active ? "gold" : "mist"}>{entry.effect.active ? entry.effect.text : `${entry.effect.text}, over`}</Badge>}
        {entry.cycle_id && entry.source === "downtime" ? (
          <Link to={`/cycles/${entry.cycle_id}`} className="hover:text-gold">
            {sourceText(entry)}
          </Link>
        ) : (
          <span>{sourceText(entry)}</span>
        )}
        {entry.logged_by_name && (
          <span>
            · logged by {entry.logged_by_name}, {dates.date(entry.logged_at)}
          </span>
        )}
        <span className="ml-auto flex gap-2">
          <ResolveButton entry={entry} />
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

/**
 * The Log influence tool (#134): add an entry by hand, for a PC, an NPC or a name
 * only, or change one. Opened on this page, on a character's page with the
 * character filled in, and beside a submission on the cycle page. Add another
 * keeps the date, cycle and character for the next entry in a batch.
 */
export function EntryForm({
  troupeId,
  choices,
  entry,
  characterId,
  cycleId,
  onDone,
}: {
  troupeId: string;
  choices: InfluenceChoicesOut;
  entry?: InfluenceEntryOut;
  /** Filled in for a new entry. */
  characterId?: string;
  cycleId?: string;
  onDone: () => void;
}) {
  const dates = useDates();
  const [form, setForm] = useState<EntryFields>({
    type: entry?.type ?? "elite",
    who: entry ? (entry.character_id ? `c:${entry.character_id}` : "name") : characterId ? `c:${characterId}` : "",
    name: entry && !entry.character_id ? entry.name : "",
    specialization: entry?.specialization ?? "",
    action_key: entry?.action_key ?? "",
    purpose: entry?.purpose ?? "",
    times: entry?.times ?? 1,
    blocks: entry?.blocks ?? 0,
    happened_at: dates.toInput(entry?.happened_at ?? new Date()),
    cycle_id: entry?.cycle_id ?? cycleId ?? "",
    needs_details: entry?.needs_details ?? false,
  });
  // The short id of the entry Add another last logged.
  const [logged, setLogged] = useState<string | null>(null);
  const [target, setTarget] = useState(targetForm(entry));
  const set = (change: Partial<EntryFields>) => setForm({ ...form, ...change });
  const type = choices.types.find((t) => t.type === form.type)!;
  const characterOf = form.who.startsWith("c:") ? form.who.slice(2) : "";
  const character = choices.characters.find((c) => c.id === characterOf);
  const standing = useQuery({
    queryKey: ["influence-standing", troupeId, characterOf, form.cycle_id],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/influence-log/characters/{character_id}", {
          params: { path: { troupe_id: troupeId, character_id: characterOf }, query: { cycle_id: form.cycle_id || undefined } },
        }),
      ),
    enabled: !!characterOf,
  });
  const held = (characterOf && standing.data?.standings.find((s) => s.type === form.type)?.held) || [];
  const specializations = specializationGroups(held, type.specializations, form.specialization);
  const cycle = choices.cycles.find((c) => c.id === form.cycle_id);
  const warning =
    !entry && character?.kind === "pc" && cycle
      ? allowanceWarning(
          standing.data?.cycle.find((u) => u.type === form.type),
          form.times,
          character.name,
          cycle.name,
        )
      : null;
  const save = useAction(async (more: boolean) => {
    const body: InfluenceEntryIn = {
      type: form.type,
      happened_at: dates.fromInput(form.happened_at).toISOString(),
      character_id: characterOf || null,
      name: form.who === "name" ? form.name : "",
      specialization: form.specialization,
      action_key: form.action_key || null,
      purpose: form.purpose,
      times: form.times,
      blocks: form.blocks,
      cycle_id: form.cycle_id || null,
      needs_details: form.needs_details,
      target: targetBody(target, form.action_key),
    };
    const saved = entry
      ? await unwrap(api.PUT("/api/influence-entries/{entry_id}", { params: { path: { entry_id: entry.id } }, body }))
      : await unwrap(api.POST("/api/troupes/{troupe_id}/influence-log", { params: { path: { troupe_id: troupeId } }, body }));
    if (more) {
      setForm(another(form));
      setTarget(targetForm(undefined));
      setLogged(saved.short_id);
    } else onDone();
  });
  // A character who has left can stay on an entry that already names them, but not be newly logged.
  const characters = choices.characters.filter((c) => c.in_troupe || `c:${c.id}` === form.who);
  const dateFrom = (value: string) => {
    const [kind, id] = value.split(":");
    const cycle = kind === "cycle" ? choices.cycles.find((c) => c.id === id) : undefined;
    const game = kind === "game" ? choices.games.find((g) => g.id === id) : undefined;
    if (cycle) set({ happened_at: dates.toInput(cycleDate(cycle)), cycle_id: form.cycle_id || cycle.id });
    else if (game) set({ happened_at: dates.toInput(game.starts_at) });
  };
  const ready = !!characterOf || (form.who === "name" && !!form.name.trim());

  return (
    <form
      aria-label={entry ? `Edit ${entry.short_id}` : "Log influence"}
      className="mb-4 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(false);
      }}
    >
      {logged && <Notice>Logged {logged}. The next one keeps the date, cycle and who took it.</Notice>}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Who">
          <WhoPicker characters={characters} who={form.who} name={form.name} onChange={(who, name) => set({ who, name })} />
        </Field>
        <Field label="Type">
          <Select value={form.type} onChange={(e) => set({ type: e.target.value as EntryFields["type"], action_key: "" })}>
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
            {specializations.own.length > 0 && (
              <optgroup label={`${character?.name ?? "Their"}'s own`}>
                {specializations.own.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </optgroup>
            )}
            <optgroup label={specializations.own.length ? "Every other" : "Every specialisation"}>
              {specializations.others.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </optgroup>
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
        <TargetFields
          choices={choices}
          actionKey={form.action_key}
          type={form.type}
          form={target}
          onChange={(change) => setTarget({ ...target, ...change })}
        />
        <Field label={`When (${dates.zoneName()})`}>
          <Input type="datetime-local" value={form.happened_at} onChange={(e) => set({ happened_at: e.target.value })} />
        </Field>
        {(choices.cycles.length > 0 || choices.games.length > 0) && (
          <Field label="Or date it by">
            <Select value="" onChange={(e) => dateFrom(e.target.value)}>
              <option value="">A cycle or a game…</option>
              {choices.cycles.length > 0 && (
                <optgroup label="Cycles">
                  {choices.cycles.map((c) => (
                    <option key={c.id} value={`cycle:${c.id}`}>
                      {c.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {choices.games.length > 0 && (
                <optgroup label="Games">
                  {choices.games.map((g) => (
                    <option key={g.id} value={`game:${g.id}`}>
                      {dates.gameStart(g.starts_at)}
                    </option>
                  ))}
                </optgroup>
              )}
            </Select>
          </Field>
        )}
        <Field label="Applies to this downtime">
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
        <Field label="Blocks already on it">
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
      {warning && <Notice>{warning}</Notice>}
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !ready}>
          {entry ? "Save changes" : "Log it"}
        </Button>
        {!entry && (
          <Button type="button" variant="secondary" title="Log this one, and start the next with the same date, cycle and who" disabled={save.isPending || !ready} onClick={() => save.mutate(true)}>
            Add another
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onDone}>
          {logged ? "Done" : "Cancel"}
        </Button>
      </div>
    </form>
  );
}
