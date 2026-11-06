import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, TitlesOut } from "../../api/types";
import { ActionMenu, MenuItem } from "../../components/ActionMenu";
import { Avatar } from "../../components/Avatar";
import { useClanName } from "../../components/ClanNames";
import { LinesVeilsNote } from "../../components/LinesVeils";
import { AtHandle } from "../../components/PersonPicker";
import { Dialog } from "../../components/Dialog";
import { Pronouns } from "../../components/PronounsInput";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { useEquipmentRules } from "./EquipmentEditor";
import { holdersLink } from "./equipmentSearch";
import { FilterBuilder } from "./FilterBuilder";
import { titleGives, titleGroups, titleStatusWords } from "./titleGroups";
import { asksEquipment, columnLabel, columnOf, columns, decode, encode, filterLabel, ready, sentence, type Group, type Names } from "./filters";
import { ageRank, clanText, nextSort, sortRows, type Sort } from "./roster";

/**
 * The troupe's characters, those whose home it is first, for its storytellers and
 * assistants: searched by name, narrowed by a filter on their sheets (kept in the
 * URL), ticked and printed.
 */
export function RosterTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const named = useClanName();
  const roster = useQuery({ queryKey: ["roster", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", path)) });
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: { troupe_id: troupeId } } })),
    staleTime: 5 * 60_000,
  });
  const titles = useQuery({ queryKey: ["titles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", path)) });
  const equipment = useEquipmentRules("vampire");
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
  // Printing sheets and badges, folded behind one button so the list starts near the top on a phone.
  const [printing, setPrinting] = useState(false);
  const [sort, setSort] = useState<Sort>(null);
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;
  if (!roster.data.length) return <Empty>No characters have joined this troupe yet.</Empty>;

  const everyone = roster.data;
  const matched = sent.items.length ? new Map((search.data ?? []).map((m) => [m.character_id, m])) : null;
  const q = query.trim().toLowerCase();
  const shown = everyone.filter(
    (e) => (!matched || matched.has(e.character_id)) && (!q || `${e.character_name} ${e.player_name} ${e.player_handle ?? ""}`.toLowerCase().includes(q)),
  );
  const names: Names = {
    category: (key) => catalogue.data?.categories.find((c) => c.key === key)?.name ?? key,
    player: (id) => everyone.find((e) => e.player_id === id)?.player_name ?? "someone",
    character: (id) => everyone.find((e) => e.character_id === id)?.character_name ?? "someone",
  };
  const characters = everyone.map((e) => ({ id: e.character_id, name: e.character_name })).sort((a, b) => a.name.localeCompare(b.name));
  // Show their equipment: the items of the home characters shown (an NPC is always the troupe's).
  const holding = shown.filter((e) => e.home || e.kind === "npc");
  const allHolding = everyone.filter((e) => (e.home || e.kind === "npc") && !e.retired);
  const sameHolders = holding.length === allHolding.length && holding.every((e) => !e.retired);
  const equipmentLink = holdersLink(
    troupeId,
    sameHolders ? [] : holding.map((e) => e.character_id),
    holding.some((e) => e.retired),
  );
  // A column for each number the filter compares, such as Occult, to line them up.
  const valueColumns = columns(sent).map((c) => ({ label: columnLabel(c, names), key: columnOf(c)! }));
  const valueOf = (e: RosterEntry, key: string) => matched?.get(e.character_id)?.values[key] ?? 0;
  const showEquipment = asksEquipment(sent);
  const sortKeys: Record<string, (e: RosterEntry) => string | number | null> = {
    character: (e) => e.character_name,
    player: (e) => (e.player_id ? e.player_name : null),
    clan: (e) => named(e.clan),
    age: (e) => ageRank(e.social_age),
    ...Object.fromEntries(valueColumns.map((c) => [`value:${c.key}`, (e: RosterEntry) => valueOf(e, c.key)])),
  };
  const rows = sortRows(shown, (sort && sortKeys[sort.by]) || null, sort?.descending ?? false);
  const sortBy = (by: string) => setSort(nextSort(sort, by));
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
        <Button variant="secondary" aria-expanded={printing} onClick={() => setPrinting(!printing)}>
          Print…{ticked.length > 0 && ` (${ticked.length} selected)`}
        </Button>
      }
    >
      {printing && (
        <div className="mb-3 flex flex-col gap-2 rounded-md border border-ash p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-full text-mist sm:w-auto">Sheets:</span>
            <Button variant="secondary" disabled={!ticked.length} onClick={() => print(ticked.map((e) => e.character_id))}>
              Print selected ({ticked.length})
            </Button>
            <Button variant="secondary" disabled={!shown.length} onClick={() => print(narrowed ? shown.map((e) => e.character_id) : undefined)}>
              Print all {shown.length}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-full text-mist sm:w-auto">Game badges:</span>
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
        </div>
      )}
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
            {filterLabel(sent)}
          </Button>
        </div>
        {building && catalogue.data && (
          <div className="rounded-md border border-ash p-3">
            <FilterBuilder
              value={filter}
              onChange={setFilter}
              choices={{ catalogue: catalogue.data, titles: titleList(titles.data), players, characters, equipment: equipment.data }}
            />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-mist">
            {shown.length} of {everyone.length} characters
            {search.isFetching && " · searching…"}
          </span>
          {holding.length > 0 && (
            <Link to={equipmentLink} className="text-xs text-gold underline hover:text-parchment">
              Show their equipment
            </Link>
          )}
          {filter.items.map((item, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full border border-ash px-2 py-0.5 text-xs">
              {named(sentence({ match: filter.match, items: [item] }, names))}
              <button
                type="button"
                aria-label={`Remove “${named(sentence({ match: filter.match, items: [item] }, names))}”`}
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
      <label className="flex items-center gap-2 border-b border-ash pb-2 text-sm text-mist lg:border-0">
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
        <table aria-label="Characters" className="w-full text-sm">
          {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
          <thead className="max-lg:sr-only">
            <tr className="border-b border-ash text-left text-xs text-mist">
              <th className="w-px py-2 pr-2 font-normal">
                <span className="sr-only">Selected</span>
              </th>
              <SortHeading label="Character" by="character" sort={sort} onSort={sortBy} />
              <SortHeading label="Player" by="player" sort={sort} onSort={sortBy} className={WIDE} />
              <SortHeading label="Clan" by="clan" sort={sort} onSort={sortBy} className={WIDE} />
              <SortHeading label="Age" by="age" sort={sort} onSort={sortBy} className={WIDE} />
              <th className={`${WIDE} py-2 pr-3 font-normal`}>Here as</th>
              <th className={`${WIDE} py-2 pr-3 font-normal`}>Flags</th>
              {valueColumns.map((c) => (
                <SortHeading key={c.key} label={c.label} by={`value:${c.key}`} sort={sort} onSort={sortBy} className={`${WIDE} text-right`} />
              ))}
              {showEquipment && <th className={`${WIDE} py-2 pr-3 font-normal`}>Equipment asked about</th>}
              <th className="py-2 font-normal">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ash">
            {rows.map((entry) => (
              <RosterRow
                key={entry.character_id}
                troupeId={troupeId}
                entry={entry}
                selected={selected.has(entry.character_id)}
                onSelect={() => toggle(entry.character_id)}
                values={valueColumns.map((c) => [c.label, valueOf(entry, c.key)])}
                equipment={showEquipment ? (matched?.get(entry.character_id)?.equipment ?? []) : null}
              />
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function titleList(titles: TitlesOut | undefined): string[] {
  return (titles?.titles ?? []).map((t) => t.name);
}

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

/** A heading that sorts the list by its column: A to Z, Z to A, then back to the
 * list's own order. On a narrow screen the headings are for screen readers only,
 * and the list keeps its own order. */
function SortHeading({ label, by, sort, onSort, className = "" }: { label: string; by: string; sort: Sort; onSort: (by: string) => void; className?: string }) {
  const on = sort?.by === by;
  return (
    <th aria-sort={on ? (sort.descending ? "descending" : "ascending") : undefined} className={`py-2 pr-3 font-normal ${className}`}>
      <span className="lg:hidden">{label}</span>
      <button type="button" className="inline-flex items-center gap-1 hover:text-parchment max-lg:hidden" onClick={() => onSort(by)}>
        {label}
        <span aria-hidden="true" className="inline-block w-2.5">
          {on ? (sort.descending ? "↓" : "↑") : ""}
        </span>
      </button>
    </th>
  );
}

/** One row per character: who it is and who plays it, its clan and social age, how it
 * stands here, what needs staff, the numbers the filter compares, and its titles and
 * XP behind ⋯, each in a dialog. */
function RosterRow({
  troupeId,
  entry,
  selected,
  onSelect,
  values,
  equipment,
}: {
  troupeId: string;
  entry: RosterEntry;
  selected: boolean;
  onSelect: () => void;
  /** The numbers the filter compares, such as ["Occult", 2]. */
  values: [string, number][];
  /** With a filter on equipment, the items it asks about that the character holds; null without one. */
  equipment: string[] | null;
}) {
  const named = useClanName();
  const [open, setOpen] = useState<"titles" | "xp" | null>(null);
  const close = () => setOpen(null);
  const name = entry.character_name;
  const clan = clanText(named(entry.clan), entry.social_age);
  const here = entry.kind === "npc" ? <Badge>NPC</Badge> : entry.home ? <Badge tone="gold">Home</Badge> : <Badge>Visiting</Badge>;
  const flags = (
    <>
      {entry.player_suspended && <Badge tone="blood">Player suspended</Badge>}
      {entry.waiting && (
        <Link to={`/troupes/${troupeId}/approvals`} className="rounded-full hover:underline">
          <Badge tone="blood">Asking to make this home</Badge>
        </Link>
      )}
      {entry.backstory_waiting && (
        <Link to={`/characters/${entry.character_id}/backstory?troupe=${troupeId}`}>
          <Badge tone="blood">Backstory to read</Badge>
        </Link>
      )}
      {entry.disciplines_waiting > 0 && (
        <Badge tone="blood">
          {entry.disciplines_waiting} discipline{entry.disciplines_waiting > 1 ? "s" : ""} to approve
        </Badge>
      )}
    </>
  );
  const represented = !entry.seated && <span className="block text-xs text-mist">Represented by: {named(entry.represented_by) ?? "nobody yet"}</span>;
  const held = equipment?.length ? equipment.join(" · ") : null;
  return (
    <tr>
      <td className="w-px py-2.5 pr-2 align-top">
        <input type="checkbox" aria-label={`Select ${name}`} checked={selected} onChange={onSelect} className="mt-1.5" />
      </td>
      <td className="py-2.5 pr-3 align-top">
        <div className="flex items-start gap-2">
          <Avatar name={name} picture={entry.picture} clan={entry.clan} />
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <Link to={`/characters/${entry.character_id}`} className="font-medium break-words hover:text-gold">
                {name}
              </Link>
              <Pronouns pronouns={entry.pronouns} />
            </span>
            {entry.player_id && (
              <span className="lg:hidden">
                <PlayerLink entry={entry} />
              </span>
            )}
            {/* What the wide columns show, folded under the name. */}
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs lg:hidden">
              <span className="text-parchment/80">
                {clan && <span>{clan}</span>}
                {clan && " · "}
                <span>{entry.social_age}</span>
              </span>
              {here}
              {flags}
            </span>
            <span className="lg:hidden">{represented}</span>
            {values.length > 0 && (
              <span className="flex flex-wrap gap-1 lg:hidden">
                {values.map(([label, value]) => (
                  <span key={label} className="rounded bg-ash px-1.5 py-0.5 text-xs text-parchment">
                    {label} {value}
                  </span>
                ))}
              </span>
            )}
            {held && (
              <span title="What it holds that the filter asks about" className="text-xs text-gold/90 lg:hidden">
                {held}
              </span>
            )}
            <HeldTitles entry={entry} />
            <LinesVeilsNote value={entry.lines_veils} who={entry.player_name} className="text-xs text-parchment/80" />
          </div>
        </div>
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{entry.player_id && <PlayerLink entry={entry} />}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-parchment/80`}>
        {clan && <span>{clan}</span>}
        {represented}
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top whitespace-nowrap text-parchment/80`}>{entry.social_age}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{here}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>
        <span className="flex flex-wrap gap-1">{flags}</span>
      </td>
      {values.map(([label, value]) => (
        <td key={label} className={`${WIDE} py-2.5 pr-3 text-right align-top tabular-nums`}>
          {value}
        </td>
      ))}
      {equipment && (
        <td title="What it holds that the filter asks about" className={`${WIDE} py-2.5 pr-3 align-top text-xs text-gold/90`}>
          {held}
        </td>
      )}
      <td className="w-px py-1.5 text-right align-top">
        <ActionMenu label={`Actions for ${name}`} variant="ghost" menuClassName="w-48">
          <MenuItem onSelect={() => setOpen("titles")}>Titles…</MenuItem>
          {entry.home && entry.kind === "pc" && <MenuItem onSelect={() => setOpen("xp")}>Award XP…</MenuItem>}
        </ActionMenu>
        {/* The dialogs sit here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
        <Dialog title={`${name}'s titles`} open={open === "titles"} onClose={close}>
          <Titles troupeId={troupeId} entry={entry} />
        </Dialog>
        <Dialog title={`Award XP to ${name}`} open={open === "xp"} onClose={close}>
          <AwardXp troupeId={troupeId} entry={entry} onDone={close} />
        </Dialog>
      </td>
    </tr>
  );
}

/** The character's player, with their handle and pronouns, linking to their profile. */
function PlayerLink({ entry }: { entry: RosterEntry }) {
  return (
    <Link to={`/players/${entry.player_id}`} className="text-xs text-mist break-words hover:text-gold lg:text-sm">
      {entry.player_name} {entry.player_handle && <AtHandle handle={entry.player_handle} />}
      <Pronouns pronouns={entry.player_pronouns} className="" />
    </Link>
  );
}

/** The titles the character holds here, to read: the active one starred, one out
 * of its sect in red. Titles… on its ⋯ gives and takes them. */
function HeldTitles({ entry }: { entry: RosterEntry }) {
  if (!entry.titles.length) return null;
  return (
    <ul aria-label={`${entry.character_name}'s titles`} className="flex flex-wrap gap-1">
      {entry.titles.map((t) => (
        <li key={t}>
          <TitlePill entry={entry} title={t} />
        </li>
      ))}
    </ul>
  );
}

function TitlePill({ entry, title, children }: { entry: RosterEntry; title: string; children?: ReactNode }) {
  const outOfSect = entry.out_of_sect_titles.includes(title);
  const active = title === entry.active_title;
  return (
    <span
      className={`inline-flex h-6 items-center gap-1 rounded-full border text-xs ${children ? "pr-1 pl-2.5" : "px-2.5"} ${
        outOfSect ? "border-blood bg-blood/15 text-blood-bright" : "border-gold/50 bg-gold/10 text-gold"
      }`}
      title={
        outOfSect
          ? `Out of sect: ${entry.character_name} is ${entry.sect ?? "of no sect"}. Kept until taken.`
          : active
            ? "Active: the title that gives status"
            : undefined
      }
    >
      {active && <span aria-hidden="true">★</span>}
      {title}
      {active && <span className="sr-only"> (active)</span>}
      {outOfSect && <span className="sr-only"> (out of sect)</span>}
      {children}
    </span>
  );
}

/** Experience for a character whose home troupe this is, in its dialog: amount and
 * reason, as the XP history shows them. */
function AwardXp({ troupeId, entry, onDone }: { troupeId: string; entry: RosterEntry; onDone: () => void }) {
  // Starts at the troupe's usual XP for a session (Starting points).
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const sessionXp = troupe.data?.session_xp ?? 8;
  const [amount, setAmount] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const award = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp", {
        params: { path: { character_id: entry.character_id } },
        body: { amount: amount ?? sessionXp, reason },
      }),
    );
    onDone();
  });
  return (
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
          value={amount ?? sessionXp}
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
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={award.isPending}>
          Award
        </Button>
      </div>
    </form>
  );
}

/** The character's titles here, in its dialog: each with × to take it away, and
 * the troupe's and the book's titles to give it another. */
function Titles({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const save = useAction((names: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/titles", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { titles: names },
      }),
    ),
  );
  return (
    <div className="flex flex-col gap-4">
      <section>
        <h3 className="mb-1 text-xs text-mist">Holds</h3>
        {entry.titles.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {entry.titles.map((t) => (
              <li key={t}>
                <TitlePill entry={entry} title={t}>
                  <button
                    type="button"
                    aria-label={`Take the title ${t} from ${entry.character_name}`}
                    className="grid h-4 w-4 place-items-center rounded-full leading-none opacity-70 hover:bg-blood hover:text-parchment hover:opacity-100 pointer-coarse:h-6 pointer-coarse:w-6"
                    disabled={save.isPending}
                    onClick={() => save.mutate(entry.titles.filter((x) => x !== t))}
                  >
                    ×
                  </button>
                </TitlePill>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-mist">No titles here yet.</p>
        )}
        <ErrorText error={save.error} />
      </section>
      <section>
        <h3 className="mb-1 text-xs text-mist">Give a title</h3>
        <GiveTitle troupeId={troupeId} entry={entry} onGive={(title) => save.mutate([...entry.titles, title])} />
      </section>
    </div>
  );
}

/** Pick one of the troupe's or the book's titles that the character can hold (of
 * its sect, or of any sect), grouped by sect, or type a new one. */
function GiveTitle({ troupeId, entry, onGive }: { troupeId: string; entry: RosterEntry; onGive: (title: string) => void }) {
  const [typed, setTyped] = useState("");
  const titles = useQuery({
    queryKey: ["titles", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const q = typed.trim().toLowerCase();
  const open = (titles.data?.titles ?? []).filter((t) => t.offered && !entry.titles.includes(t.name) && (t.sect === null || t.sect === entry.sect));
  const matching = open.filter((t) => t.name.toLowerCase().includes(q));
  const choices = matching.map((t) => t.name);
  const exact = choices.some((t) => t.toLowerCase() === q);
  const give = (title: string) => {
    onGive(title);
    setTyped("");
  };
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (typed.trim()) give(choices.find((t) => t.toLowerCase() === q) ?? typed.trim());
      }}
    >
      <Input autoFocus aria-label="Title" placeholder="Search or type a new title…" value={typed} onChange={(e) => setTyped(e.target.value)} />
      <p className="text-xs text-mist">
        {entry.sect
          ? `${entry.character_name} is ${entry.sect}: ${entry.sect} titles and those of any sect.`
          : `${entry.character_name} has no sect: only titles of any sect.`}
      </p>
      <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
        {titleGroups(entry.sect ? [entry.sect] : [], matching).map(([sect, list]) => (
          <section key={sect ?? ""}>
            <h3 className="mb-1 text-xs text-mist">{sect ?? "Any sect"}</h3>
            <ul className="flex flex-wrap gap-1.5">
              {list.map((t) => (
                <li key={t.name}>
                  <button
                    type="button"
                    className="rounded-full border border-ash px-2.5 py-1 text-xs hover:border-gold hover:text-gold"
                    title={titleGives(titleStatusWords(t), t)}
                    onClick={() => give(t.name)}
                  >
                    {t.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {titles.isPending && <p className="text-sm text-mist">Loading…</p>}
      </div>
      {q && !exact && (
        <Button type="submit" variant="secondary">
          Give the new title “{typed.trim()}”
        </Button>
      )}
    </form>
  );
}
