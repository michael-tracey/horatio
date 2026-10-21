import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, TitlesOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { AtHandle } from "../../components/PersonPicker";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { FilterBuilder } from "./FilterBuilder";
import { columnLabel, columnOf, columns, decode, encode, ready, sentence, type Group, type Names } from "./filters";

/**
 * The troupe's characters, those whose home it is first, for its storytellers and
 * assistants: searched by name, narrowed by a filter on their sheets (kept in the
 * URL), ticked and printed.
 */
export function RosterTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const roster = useQuery({ queryKey: ["roster", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", path)) });
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: { troupe_id: troupeId } } })),
    staleTime: 5 * 60_000,
  });
  const titles = useQuery({ queryKey: ["titles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", path)) });
  const [params, setParams] = useSearchParams();
  const filter = decode(params.get("filter"));
  const setFilter = (group: Group) =>
    setParams(
      (p) => {
        p.set("filter", encode(group));
        return p;
      },
      { replace: true },
    );
  const sent = ready(filter);
  const search = useQuery({
    queryKey: ["roster-search", troupeId, encode(sent)],
    queryFn: () => unwrap(api.POST("/api/troupes/{troupe_id}/characters/search", { ...path, body: sent })),
    enabled: sent.items.length > 0,
    placeholderData: (previous) => previous,
  });
  const [query, setQuery] = useState("");
  const [building, setBuilding] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;
  if (!roster.data.length) return <Empty>No characters have joined this troupe yet.</Empty>;

  const everyone = roster.data;
  const matched = sent.items.length ? new Map((search.data ?? []).map((m) => [m.character_id, m.values])) : null;
  const q = query.trim().toLowerCase();
  const shown = everyone.filter(
    (e) => (!matched || matched.has(e.character_id)) && (!q || `${e.character_name} ${e.player_name} ${e.player_handle ?? ""}`.toLowerCase().includes(q)),
  );
  const names: Names = {
    category: (key) => catalogue.data?.categories.find((c) => c.key === key)?.name ?? key,
    player: (id) => everyone.find((e) => e.player_id === id)?.player_name ?? "someone",
  };
  const shownColumns = columns(sent);
  const players = [...new Map(everyone.filter((e) => e.player_id).map((e) => [e.player_id!, e.player_name])).entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));

  // Ticks stay when the filter changes; Print selected prints them all, hidden or not.
  const ticked = everyone.filter((e) => selected.has(e.character_id));
  const tickedShown = shown.filter((e) => selected.has(e.character_id));
  const allTicked = shown.length > 0 && tickedShown.length === shown.length;
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (!next.delete(id)) next.add(id);
    setSelected(next);
  };
  // Opened in a new tab, so the list (and what is ticked) stays as it was.
  const print = (ids?: string[]) =>
    window.open(`/print/troupes/${troupeId}${ids ? `?characters=${ids.join(",")}` : ""}`, "_blank", "noopener");
  const narrowed = shown.length !== everyone.length;
  const badges = (ids?: string[]) =>
    window.open(`/print/troupes/${troupeId}/badges${ids ? `?characters=${ids.join(",")}` : ""}`, "_blank", "noopener");

  return (
    <Card
      title="Characters"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!ticked.length} onClick={() => print(ticked.map((e) => e.character_id))}>
            Print selected ({ticked.length})
          </Button>
          <Button variant="secondary" disabled={!shown.length} onClick={() => print(narrowed ? shown.map((e) => e.character_id) : undefined)}>
            Print all {shown.length}
          </Button>
        </div>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-mist">Game badges:</span>
        <Button variant="secondary" disabled={!ticked.length} onClick={() => badges(ticked.map((e) => e.character_id))}>
          Badges for selected ({ticked.length})
        </Button>
        <Button variant="secondary" disabled={!shown.length} onClick={() => badges(narrowed ? shown.map((e) => e.character_id) : undefined)}>
          Badges for all {shown.length}
        </Button>
        <Button variant="ghost" onClick={() => window.open(`/print/troupes/${troupeId}/staff-badges`, "_blank", "noopener")}>
          Storyteller badges
        </Button>
      </div>
      <div className="mb-3 flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            type="search"
            aria-label="Search characters"
            placeholder="Character or player name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-40 flex-1"
          />
          <Button variant={building ? "primary" : "secondary"} aria-expanded={building} onClick={() => setBuilding(!building)}>
            Filter{sent.items.length ? ` (${sent.items.length})` : ""}
          </Button>
        </div>
        {building && catalogue.data && (
          <div className="rounded-md border border-ash p-3">
            <FilterBuilder value={filter} onChange={setFilter} choices={{ catalogue: catalogue.data, titles: titleList(titles.data), players }} />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-mist">
            {shown.length} of {everyone.length} characters
            {search.isFetching && " · searching…"}
          </span>
          {filter.items.map((item, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full border border-ash px-2 py-0.5 text-xs">
              {sentence({ match: filter.match, items: [item] }, names)}
              <button
                type="button"
                aria-label={`Remove “${sentence({ match: filter.match, items: [item] }, names)}”`}
                className="text-mist hover:text-parchment"
                onClick={() => setFilter({ ...filter, items: filter.items.filter((_, j) => j !== i) })}
              >
                ×
              </button>
            </span>
          ))}
          {filter.items.length > 1 && <span className="text-xs text-mist">({filter.match === "all" ? "all of these" : "any of these"})</span>}
          {filter.items.length > 0 && (
            <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => setFilter({ match: "all", items: [] })}>
              Show everyone
            </button>
          )}
        </div>
        <ErrorText error={search.error} />
      </div>
      <label className="flex items-center gap-2 border-b border-ash pb-2 text-sm text-mist">
        <input
          type="checkbox"
          checked={allTicked}
          ref={(box) => {
            if (box) box.indeterminate = tickedShown.length > 0 && !allTicked;
          }}
          onChange={() => {
            const next = new Set(selected);
            for (const e of shown) {
              if (allTicked) next.delete(e.character_id);
              else next.add(e.character_id);
            }
            setSelected(next);
          }}
        />
        Select all shown
        {ticked.length > tickedShown.length && <span className="text-xs">· {ticked.length - tickedShown.length} selected but hidden by the filter</span>}
      </label>
      {shown.length === 0 ? (
        <p className="py-3 text-sm text-mist">No characters match.</p>
      ) : (
        <ul className="divide-y divide-ash">
          {shown.map((entry) => (
            <RosterRow
              key={entry.character_id}
              troupeId={troupeId}
              entry={entry}
              selected={selected.has(entry.character_id)}
              onSelect={() => toggle(entry.character_id)}
              values={shownColumns.map((c) => [columnLabel(c, names), matched?.get(entry.character_id)?.[columnOf(c)!] ?? 0])}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function titleList(titles: TitlesOut | undefined): string[] {
  return [...new Set([...(titles?.catalogue ?? []), ...(titles?.troupe ?? [])])].sort();
}

/** One line per character: who it is, its clan and social age, how it stands
 * here, and its titles, with + to give another. */
function RosterRow({
  troupeId,
  entry,
  selected,
  onSelect,
  values,
}: {
  troupeId: string;
  entry: RosterEntry;
  selected: boolean;
  onSelect: () => void;
  /** The numbers the filter compares, such as ["Occult", 2]. */
  values: [string, number][];
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
      <input type="checkbox" aria-label={`Select ${entry.character_name}`} checked={selected} onChange={onSelect} />
      <Avatar name={entry.character_name} picture={entry.picture} clan={entry.clan} />
      <span className="flex min-w-0 items-baseline gap-2">
        <Link to={`/characters/${entry.character_id}`} className="truncate font-medium hover:text-gold">
          {entry.character_name}
        </Link>
        {entry.player_id && (
          <Link to={`/players/${entry.player_id}`} className="truncate text-xs text-mist hover:text-gold">
            {entry.player_name} {entry.player_handle && <AtHandle handle={entry.player_handle} />}
          </Link>
        )}
      </span>
      <span className="text-xs whitespace-nowrap text-parchment/80">
        {entry.clan ?? "No clan yet"} · {entry.social_age}
      </span>
      {entry.kind === "npc" ? <Badge>NPC</Badge> : entry.home ? <Badge tone="gold">home</Badge> : <Badge>visiting</Badge>}
      {entry.waiting && <Badge tone="blood">asking to make this home</Badge>}
      {entry.disciplines_waiting > 0 && (
        <Badge tone="blood">
          {entry.disciplines_waiting} discipline{entry.disciplines_waiting > 1 ? "s" : ""} to approve
        </Badge>
      )}
      {values.map(([label, value]) => (
        <span key={label} className="rounded bg-ash px-1.5 py-0.5 text-xs text-parchment">
          {label} {value}
        </span>
      ))}
      <span className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
        <Titles troupeId={troupeId} entry={entry} />
        {entry.home && entry.kind === "pc" && <AwardXp troupeId={troupeId} entry={entry} />}
      </span>
    </li>
  );
}

/** Experience for a character whose home troupe this is, in a dialog: amount and
 * reason, as the XP history shows them. */
function AwardXp({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  // Starts at the troupe's usual XP for a session (Starting points).
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const sessionXp = troupe.data?.session_xp ?? 8;
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(sessionXp);
  const [reason, setReason] = useState("");
  const award = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp", {
        params: { path: { character_id: entry.character_id } },
        body: { amount, reason },
      }),
    );
    setOpen(false);
    setReason("");
  });
  return (
    <>
      <button
        type="button"
        aria-label={`Award XP to ${entry.character_name}`}
        title="Award XP"
        className="h-6 rounded border border-ash px-1.5 text-xs text-mist hover:border-mist hover:text-parchment"
        onClick={() => {
          setAmount(sessionXp);
          setOpen(true);
        }}
      >
        +XP
      </button>
      <Dialog title={`Award XP to ${entry.character_name}`} open={open} onClose={() => setOpen(false)}>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            award.mutate(undefined);
          }}
        >
          <div className="flex gap-2">
            <Input
              aria-label={`XP for ${entry.character_name}`}
              type="number"
              min={1}
              required
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="w-20"
            />
            <Input
              aria-label={`Reason for ${entry.character_name}'s XP`}
              placeholder="Reason, such as a game"
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="min-w-0 flex-1"
            />
          </div>
          <ErrorText error={award.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={award.isPending}>
              Award
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

/** The character's titles here as pills, each with × to take it away, and a +
 * square that opens a dialog to give another. */
function Titles({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const [open, setOpen] = useState(false);
  const save = useAction((names: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/titles", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { titles: names },
      }),
    ),
  );
  return (
    <>
      {entry.titles.map((t) => (
        <span key={t} className="inline-flex h-6 items-center gap-1 rounded-full border border-gold/50 bg-gold/10 pr-1 pl-2.5 text-xs text-gold">
          {t}
          <button
            type="button"
            aria-label={`Take the title ${t} from ${entry.character_name}`}
            className="grid h-4 w-4 place-items-center rounded-full leading-none text-gold/70 hover:bg-blood hover:text-parchment"
            onClick={() => save.mutate(entry.titles.filter((x) => x !== t))}
          >
            ×
          </button>
        </span>
      ))}
      <button
        type="button"
        aria-label={`Give ${entry.character_name} a title`}
        title="Give a title"
        className="grid h-6 w-6 place-items-center rounded border border-ash text-sm leading-none text-mist hover:border-gold hover:text-gold"
        onClick={() => setOpen(true)}
      >
        +
      </button>
      <ErrorText error={save.error} />
      <Dialog title={`Give ${entry.character_name} a title`} open={open} onClose={() => setOpen(false)}>
        <GiveTitle
          troupeId={troupeId}
          entry={entry}
          onGive={(title) => {
            save.mutate([...entry.titles, title]);
            setOpen(false);
          }}
        />
      </Dialog>
    </>
  );
}

/** Pick one of the troupe's or the book's titles, or type a new one. */
function GiveTitle({ troupeId, entry, onGive }: { troupeId: string; entry: RosterEntry; onGive: (title: string) => void }) {
  const [typed, setTyped] = useState("");
  const titles = useQuery({
    queryKey: ["titles", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const q = typed.trim().toLowerCase();
  const choices = titleList(titles.data).filter((t) => !entry.titles.includes(t) && t.toLowerCase().includes(q));
  const exact = choices.some((t) => t.toLowerCase() === q);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (typed.trim()) onGive(choices.find((t) => t.toLowerCase() === q) ?? typed.trim());
      }}
    >
      <Input autoFocus aria-label="Title" placeholder="Search or type a new title…" value={typed} onChange={(e) => setTyped(e.target.value)} />
      <ul className="flex max-h-64 flex-wrap gap-1.5 overflow-y-auto">
        {choices.map((t) => (
          <li key={t}>
            <button
              type="button"
              className="rounded-full border border-ash px-2.5 py-1 text-xs hover:border-gold hover:text-gold"
              onClick={() => onGive(t)}
            >
              {t}
            </button>
          </li>
        ))}
        {titles.isPending && <li className="text-sm text-mist">Loading…</li>}
      </ul>
      {q && !exact && (
        <Button type="submit" variant="secondary">
          Give the new title “{typed.trim()}”
        </Button>
      )}
    </form>
  );
}
