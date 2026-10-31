import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, HistoryEntryOut, InfluenceStandingOut } from "../../api/types";
import { EmptyState, FilterBar } from "../../components/EmptyState";
import { InfoButton } from "../../components/InfoButton";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { offered, reachNote, TYPE_NAMES } from "../../influence";
import { LogInfluenceButton } from "../troupe/LogInfluence";
import { blocksText, filterHistory, historySource, monthText, NO_HISTORY_FILTERS, thisMonth, type HistoryFilters } from "./influenceHistory";

/**
 * The character's own influence actions, newest first, from every troupe it has
 * acted in: for its player, and its home troupe's storytellers and assistants.
 * Never another character's, nor blocks anyone else placed.
 */
export function InfluenceTab({ character, mine }: { character: CharacterOut; mine: boolean }) {
  const dates = useDates();
  const [filters, setFilters] = useState<HistoryFilters>(NO_HISTORY_FILTERS);
  const history = useQuery({
    queryKey: ["influence-history", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/influence", { params: { path: { character_id: character.id } } })),
  });
  if (history.isPending) return <Loading />;
  if (history.error) return <ErrorText error={history.error} />;
  const h = history.data;
  const set = (change: Partial<HistoryFilters>) => setFilters({ ...filters, ...change });
  const month = thisMonth(h, dates);
  const specializations = [...new Set(h.entries.filter((e) => !filters.type || e.type === filters.type).map((e) => e.specialization))]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
  const shown = filterHistory(h.entries, filters, dates);
  const filtered = JSON.stringify(filters) !== JSON.stringify(NO_HISTORY_FILTERS);

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Influence"
        info={
          <InfoButton label="About influence">
            Every influence action {character.name} has taken, wherever it was logged. Each dot of influence is one action a month.
          </InfoButton>
        }
        actions={h.log_troupe_id && <LogInfluenceButton troupeId={h.log_troupe_id} characterId={character.id} label={`Log influence for ${character.name}`} />}
      >
        <section aria-label="This month">
          <h3 className="mb-1 font-sans text-xs text-mist uppercase">This month</h3>
          {month.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {month.map((line) => (
                <li key={line.type}>
                  <strong className="text-gold">{line.name}:</strong> {monthText(line)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-mist">No Elite or Underworld influence.</p>
          )}
        </section>
        {h.entries.length === 0 && (
          <div className="mt-3 border-t border-ash pt-2">
            <EmptyState title={`${character.name} has no influence actions logged yet.`}>
              An action taken in a downtime or spent at a game shows here once it is logged.
            </EmptyState>
          </div>
        )}
      </Card>
      <FilterBar count={h.entries.length} filtering={filtered}>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Type">
            <Select value={filters.type} onChange={(e) => set({ type: e.target.value as HistoryFilters["type"], specialization: "" })}>
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
          <Field label="From">
            <Input type="date" value={filters.from} onChange={(e) => set({ from: e.target.value })} />
          </Field>
          <Field label="To">
            <Input type="date" value={filters.to} onChange={(e) => set({ to: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm" title="What a Gossip or Word on the Street could still turn up">
            <input type="checkbox" checked={filters.findable} onChange={(e) => set({ findable: e.target.checked })} />
            Findable now (last {h.lookback_days} days)
          </label>
        </div>
      </FilterBar>
      {h.entries.length === 0 ? null : shown.length === 0 ? (
        <Empty>No influence actions match these filters.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {shown.map((entry) => (
            <HistoryRow
              key={entry.id}
              entry={entry}
              characterId={character.id}
              mine={mine}
              staffHere={h.log_troupe_id === entry.troupe_id}
              standing={h.standings.find((s) => s.type === entry.type)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function HistoryRow({
  entry,
  characterId,
  mine,
  staffHere,
  standing,
}: {
  entry: HistoryEntryOut;
  characterId: string;
  mine: boolean;
  staffHere: boolean;
  standing: InfluenceStandingOut | undefined;
}) {
  const dates = useDates();
  const source = historySource(entry);
  const blocks = blocksText(entry.own_blocks);
  const to =
    entry.source === "game"
      ? `/play/characters/${characterId}`
      : entry.cycle_id && staffHere
        ? `/cycles/${entry.cycle_id}`
        : entry.source === "downtime" && mine
          ? `/characters/${characterId}/results`
          : null;
  return (
    <li className="flex flex-col gap-2 rounded-md border border-ash bg-dusk p-3 text-sm" aria-label={`Entry ${entry.short_id}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <strong className="text-gold">{entry.short_id}</strong>
        <time dateTime={entry.happened_at}>{dates.dateTime(entry.happened_at)}</time>
        <span className="text-mist">
          · {TYPE_NAMES[entry.type]}
          {entry.specialization && `, ${entry.specialization}`} · {entry.action}
        </span>
      </div>
      {entry.purpose && <p>{entry.purpose}</p>}
      <div className="flex flex-wrap items-center gap-2 text-xs text-mist">
        {entry.times > 1 && <Badge tone="gold">taken {entry.times} times</Badge>}
        {blocks && <Badge>{blocks}</Badge>}
        {entry.needs_details && <Badge tone="blood">needs details</Badge>}
        {entry.other_troupe && <Badge>in {entry.troupe_name}</Badge>}
        {to ? (
          <Link to={to} className="hover:text-gold">
            {source}
          </Link>
        ) : (
          <span>{source}</span>
        )}
      </div>
      {entry.can_finish && standing && <FinishForm entry={entry} characterId={characterId} standing={standing} />}
    </li>
  );
}

/** A game entry logged without its details, finished by the player while the game goes on. */
function FinishForm({ entry, characterId, standing }: { entry: HistoryEntryOut; characterId: string; standing: InfluenceStandingOut }) {
  const [form, setForm] = useState({ specialization: "", action_key: "", purpose: "" });
  const set = (change: Partial<typeof form>) => setForm({ ...form, ...change });
  const actions = offered(standing, form.specialization);
  const chosen = actions.find((a) => a.key === form.action_key);
  const note = reachNote(standing, form.specialization, chosen);
  const finish = useAction(() =>
    unwrap(api.PUT("/api/characters/{character_id}/influence/{entry_id}", { params: { path: { character_id: characterId, entry_id: entry.id } }, body: form })),
  );
  const own = standing.held;
  const others = standing.options.filter((s) => !own.includes(s));
  return (
    <form
      aria-label={`Finish ${entry.short_id}`}
      className="flex flex-col gap-2 border-t border-ash pt-2"
      onSubmit={(e) => {
        e.preventDefault();
        finish.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">Spent at a game without its details. Add them before the game ends; after that, only staff can.</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <Field label="Specialisation">
          <Select
            value={form.specialization}
            onChange={(e) => {
              const specialization = e.target.value;
              const still = offered(standing, specialization).some((a) => a.key === form.action_key);
              set({ specialization, action_key: still ? form.action_key : "" });
            }}
          >
            <option value="">None</option>
            {own.length > 0 && (
              <optgroup label="Your own">
                {own.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </optgroup>
            )}
            {others.length > 0 && (
              <optgroup label="Others">
                {others.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </optgroup>
            )}
          </Select>
        </Field>
        <Field label="Action" hint={note}>
          <Select value={form.action_key} onChange={(e) => set({ action_key: e.target.value })}>
            <option value="">Choose…</option>
            {actions.map((a) => (
              <option key={a.key} value={a.key}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Purpose">
          <Input value={form.purpose} onChange={(e) => set({ purpose: e.target.value })} />
        </Field>
      </div>
      <ErrorText error={finish.error} />
      <Button type="submit" className="self-start" disabled={finish.isPending || !form.action_key}>
        Save details
      </Button>
    </form>
  );
}
