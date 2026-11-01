import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { DateInput } from "../../components/DateInput";
import { PersonPicker } from "../../components/PersonPicker";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { auditQuery, exportHref, filtersFrom, NO_FILTERS, toParams, type AuditCharacter, type AuditEntry, type AuditFilters } from "./audit";

/**
 * The whole audit log, for the custodian: every change in every troupe and outside
 * them, newest first, found by who made it, the character, the troupe, the kind of
 * change, the days and the words. The filters live in the page's address, so a
 * search can be shared or come back to. It only reads the log.
 */
export function AuditTab() {
  const [params, setParams] = useSearchParams();
  const applied = filtersFrom(params);
  const dates = useDates();
  const query = auditQuery(applied, dates.fromInput);
  const log = useInfiniteQuery({
    queryKey: ["audit", query],
    queryFn: ({ pageParam }) => unwrap(api.GET("/api/audit", { params: { query: { ...query, before: pageParam } } })),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next ?? undefined,
  });
  const entries = log.data?.pages.flatMap((page) => page.entries) ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* Filled in afresh whenever the address changes, by a search or by Back. */}
      <SearchForm key={params.toString()} applied={applied} onSearch={(filters) => setParams(toParams(filters))} />
      <Card
        title="Found"
        actions={
          entries.length > 0 && (
            <a href={exportHref(query)} download className="text-sm text-gold hover:underline">
              Export as CSV
            </a>
          )
        }
      >
        {log.isPending ? (
          <Loading />
        ) : log.error ? (
          <ErrorText error={log.error} />
        ) : entries.length ? (
          <>
            <ol className="divide-y divide-ash/50 text-sm" aria-label="Audit log">
              {entries.map((entry) => (
                <Entry key={entry.id} entry={entry} />
              ))}
            </ol>
            {log.hasNextPage && (
              <Button type="button" variant="secondary" className="mt-3" disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>
                {log.isFetchingNextPage ? "Loading…" : "Show older"}
              </Button>
            )}
          </>
        ) : (
          <Empty>Nothing in the log matches.</Empty>
        )}
      </Card>
    </div>
  );
}

function SearchForm({ applied, onSearch }: { applied: AuditFilters; onSearch: (filters: AuditFilters) => void }) {
  const [draft, setDraft] = useState(applied);
  const set = (change: Partial<AuditFilters>) => setDraft((d) => ({ ...d, ...change }));
  const choices = useQuery({ queryKey: ["audit-filters"], queryFn: () => unwrap(api.GET("/api/audit/filters")) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSearch(draft);
  };

  return (
    <Card title="Search the audit log">
      <p className="mb-3 text-sm text-mist">Every change in every troupe, and outside them, newest first. Searching changes nothing in the log.</p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Who did it">
            <PersonPicker value={draft.person} onChange={(person) => set({ person })} />
          </Field>
          <Field label="Character">
            <CharacterPicker value={draft.character} onChange={(character) => set({ character })} />
          </Field>
          <Field label="Troupe">
            <Select value={draft.troupe} onChange={(e) => set({ troupe: e.target.value })}>
              <option value="">Any troupe</option>
              {choices.data?.troupes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.archived ? `${t.name} (archived)` : t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Kind of change">
            <Select value={draft.group} onChange={(e) => set({ group: e.target.value })}>
              <option value="">Any change</option>
              {choices.data?.groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {g.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="From">
            <DateInput value={draft.from} max={draft.to || undefined} onChange={(e) => set({ from: e.target.value })} />
          </Field>
          <Field label="To">
            <DateInput value={draft.to} min={draft.from || undefined} onChange={(e) => set({ to: e.target.value })} />
          </Field>
        </div>
        <Field label="Words" hint="Each word somewhere in what the change says, such as a name, a trait or a reason.">
          <Input type="search" value={draft.words} onChange={(e) => set({ words: e.target.value })} />
        </Field>
        <ErrorText error={choices.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit">Search</Button>
          <Button type="button" variant="ghost" onClick={() => onSearch(NO_FILTERS)}>
            Clear
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** One change: when, who, in which troupe, and what, each leading to its own page. */
function Entry({ entry }: { entry: AuditEntry }) {
  const dates = useDates();
  const character = entry.character_id ? `/characters/${entry.character_id}${entry.troupe_id ? `?troupe=${entry.troupe_id}` : ""}` : null;
  return (
    <li className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
      <span className="flex shrink-0 flex-wrap gap-x-3 text-xs text-mist sm:w-96 sm:text-sm">
        <time dateTime={entry.at} className="whitespace-nowrap">
          {dates.dateTime(entry.at)}
        </time>
        {entry.actor_id && entry.actor_name ? (
          <Link className="hover:text-gold" to={`/players/${entry.actor_id}`}>
            {entry.actor_name}
          </Link>
        ) : (
          <span>{entry.actor_name ?? "Horatio"}</span>
        )}
        {entry.troupe_id && (
          <Link className="hover:text-gold" to={`/troupes/${entry.troupe_id}`}>
            {entry.troupe_name}
          </Link>
        )}
      </span>
      <span>
        {character ? (
          <Link className="hover:text-gold" to={character}>
            {entry.message}
          </Link>
        ) : (
          entry.message
        )}
      </span>
    </li>
  );
}

/** Whose and where a character is, to tell two of the same name apart. */
function aboutCharacter(c: AuditCharacter): string {
  return [c.kind === "npc" ? "NPC" : c.player_name, c.troupe_name ?? "no troupe", c.retired && "retired"].filter(Boolean).join(" · ");
}

/**
 * Pick any character, whosever and wherever it is: a box that lists them as it is
 * focused, typing narrowing it by name. The value is the character's id, or "".
 */
function CharacterPicker({ value, onChange, id, "aria-describedby": describedBy }: { value: string; onChange: (id: string) => void; id?: string; "aria-describedby"?: string }) {
  const listId = useId();
  // What is typed; null while the box shows the character picked.
  const [text, setText] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  const q = useDeferredValue(text ?? "");
  const found = useQuery({
    queryKey: ["audit-characters", q],
    queryFn: () => unwrap(api.GET("/api/audit/characters", { params: { query: { q } } })),
    enabled: open,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const picked = useQuery({
    queryKey: ["audit-character", value],
    queryFn: () => unwrap(api.GET("/api/audit/characters", { params: { query: { character_id: value } } })),
    enabled: !!value,
    staleTime: 300_000,
  });
  const options = found.data ?? [];
  const show = () => {
    clearTimeout(closing.current);
    setOpen(true);
  };
  const pick = (c: AuditCharacter) => {
    onChange(c.id);
    setText(null);
    setOpen(false);
    setActive(-1);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && options.length) {
      e.preventDefault();
      if (!open) return show();
      setActive((a) => (a + (e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
    } else if (e.key === "Enter" && open && options[active]) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <Input
        id={id}
        aria-describedby={describedBy}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder="Any character"
        value={text ?? (value ? (picked.data?.[0]?.name ?? "") : "")}
        className="pr-8"
        onChange={(e) => {
          setText(e.target.value);
          if (value) onChange("");
          show();
          setActive(-1);
        }}
        onFocus={show}
        onClick={show}
        // Late enough that a click in the list lands first. Words typed but not
        // picked are let go: the search is by a character, not by a name.
        onBlur={() => {
          closing.current = setTimeout(() => {
            setOpen(false);
            setText(null);
          }, 150);
        }}
        onKeyDown={onKeyDown}
      />
      <span aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-mist">
        ▾
      </span>
      {open && (
        <div onMouseDown={(e) => e.preventDefault()} className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg">
          <ul id={listId} role="listbox" aria-label="Characters">
            {options.map((c, i) => (
              <li
                key={c.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onClick={() => pick(c)}
                className={`flex cursor-pointer flex-col px-3 py-2 text-sm ${i === active ? "bg-gold/20 text-gold" : "hover:bg-night"}`}
              >
                <span className="truncate">{c.name}</span>
                <span className="truncate text-xs text-mist">{aboutCharacter(c)}</span>
              </li>
            ))}
          </ul>
          {found.isPending ? (
            <p className="px-3 py-2 text-sm text-mist">Finding characters…</p>
          ) : found.isError ? (
            <p className="px-3 py-2 text-sm text-mist">{found.error.message}</p>
          ) : (
            options.length === 0 && <p className="px-3 py-2 text-sm text-mist">No character has that name.</p>
          )}
        </div>
      )}
    </div>
  );
}
