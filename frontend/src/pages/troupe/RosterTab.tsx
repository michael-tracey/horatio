import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, TitlesOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { useClanName } from "../../components/ClanNames";
import { LinesVeilsNote } from "../../components/LinesVeils";
import { AtHandle } from "../../components/PersonPicker";
import { Pronouns } from "../../components/PronounsInput";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading, Select } from "../../components/ui";
import { useEquipmentRules } from "./EquipmentEditor";
import { holdersLink } from "./equipmentSearch";
import { FilterBuilder } from "./FilterBuilder";
import { asksEquipment, columnLabel, columnOf, columns, decode, encode, filterLabel, ready, sentence, type Group, type Names } from "./filters";
import { NewNpc } from "./NewNpc";
import { FORM_NAMES, filterNpcs, kindsIn, type NpcFilter, type NpcForm } from "./npcKinds";
import { ageRank, clanText, nextSort, showOf, shows, sortRows, type Show, type Sort } from "./roster";
import { StaffActions, TitlePill, useStaffing } from "./StaffActions";
import type { Staffing } from "./staffActions";

/** What the list is called, in its count, for each choice of Show. */
const SHOW_NAMES: Record<Show, [string, string]> = {
  pcs: ["Player characters", "player characters"],
  npcs: ["NPCs", "NPCs"],
  everyone: ["Everyone", "characters"],
};

/**
 * The troupe's characters, those whose home it is first, for its storytellers and
 * assistants: its player characters, its NPCs or both (#556), searched by name,
 * narrowed by a filter on their sheets (kept in the URL), ticked and printed. With
 * NPCs shown come their kind, form and Stock rating, and the way to make another.
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
  // Each in the address, so a list can be bookmarked or shared; "" takes it out.
  const setParam = (key: string, value: string) =>
    setParams(
      (p) => {
        if (value) p.set(key, value);
        else p.delete(key);
        return p;
      },
      { replace: true },
    );
  const setFilter = (group: Group) => setParam("filter", encode(group));
  const show = showOf(params.get("show"));
  const withNpcs = show !== "pcs";
  const npcFilter: NpcFilter = { kind: params.get("kind") ?? "", form: (params.get("form") ?? "") as NpcFilter["form"] };
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
  const [making, setMaking] = useState(false);
  const [sort, setSort] = useState<Sort>(null);
  const staffing = useStaffing(troupeId);
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;

  const everyone = roster.data;
  // Player characters, NPCs or both; then the NPCs' kind and form; then the sheet filter and the search.
  const inShow = everyone.filter((e) => shows(show, e.kind));
  const npcsInShow = inShow.filter((e) => e.kind === "npc");
  const byKind = withNpcs ? filterNpcs(inShow, npcFilter) : inShow;
  const matched = sent.items.length ? new Map((search.data ?? []).map((m) => [m.character_id, m])) : null;
  const q = query.trim().toLowerCase();
  const shown = byKind.filter(
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
  // The NPCs alone have columns of their own; player characters and everyone share the roster's.
  const npcColumns = show === "npcs";
  // Only a column shown sorts the list.
  const sortKeys: Record<string, (e: RosterEntry) => string | number | null> = {
    character: (e) => e.character_name,
    ...(npcColumns
      ? {
          kind: (e: RosterEntry) => e.npc_kind_name,
          form: (e: RosterEntry) => e.npc_form,
          rating: (e: RosterEntry) => e.stock_rating,
          listed: (e: RosterEntry) => (e.on_whos_who ? 0 : 1),
        }
      : {
          player: (e: RosterEntry) => (e.player_id ? e.player_name : null),
          clan: (e: RosterEntry) => named(e.clan),
          age: (e: RosterEntry) => ageRank(e.social_age),
        }),
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
  const showNoun = SHOW_NAMES[show][1];
  const badges = (ids?: string[]) =>
    window.open(`/print/troupes/${troupeId}/badges${ids ? `?characters=${ids.join(",")}` : ""}`, "_blank", "noopener");

  return (
    <Card
      title="Characters"
      actions={
        <span className="flex flex-wrap justify-end gap-2">
          {withNpcs && (
            <Button variant={making ? "primary" : "secondary"} aria-expanded={making} onClick={() => setMaking(!making)}>
              New NPC
            </Button>
          )}
          <Button variant="secondary" aria-expanded={printing} onClick={() => setPrinting(!printing)}>
            Print…{ticked.length > 0 && ` (${ticked.length} selected)`}
          </Button>
        </span>
      }
    >
      {withNpcs && making && (
        <section aria-labelledby="new-npc" className="mb-3 rounded-md border border-ash p-3">
          <h3 id="new-npc" className="mb-2 font-medium">
            New NPC
          </h3>
          <div className="max-w-md">
            <NewNpc troupeId={troupeId} />
          </div>
        </section>
      )}
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
        <div className="flex flex-wrap items-center gap-2">
          <ShowChoice show={show} onChange={(next) => setParam("show", next === "pcs" ? "" : next)} />
          {withNpcs && npcsInShow.length > 0 && (
            <>
              <Select aria-label="Show kind" className="w-auto text-sm" value={npcFilter.kind} onChange={(e) => setParam("kind", e.target.value)}>
                <option value="">All kinds</option>
                {kindsIn(npcsInShow).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
              <Select aria-label="Show form" className="w-auto text-sm" value={npcFilter.form} onChange={(e) => setParam("form", e.target.value)}>
                <option value="">Sheeted and Stock</option>
                <option value="sheeted">Sheeted only</option>
                <option value="stock">Stock only</option>
              </Select>
            </>
          )}
        </div>
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
            {shown.length} of {inShow.length} {showNoun}
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
              Clear all
            </button>
          )}
        </div>
        <ErrorText error={search.error} />
      </div>
      {inShow.length > 0 && (
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
      )}
      {inShow.length === 0 ? (
        <Empty>{show === "npcs" ? "No NPCs yet." : show === "pcs" ? "No player characters have joined this troupe yet." : "No characters have joined this troupe yet."}</Empty>
      ) : shown.length === 0 ? (
        <p className="py-3 text-sm text-mist">{byKind.length === 0 ? "No NPCs of that kind." : "No characters match."}</p>
      ) : (
        <table aria-label={show === "npcs" ? "NPCs" : "Characters"} className="w-full text-sm">
          {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
          <thead className="max-lg:sr-only">
            <tr className="border-b border-ash text-left text-xs text-mist">
              <th className="w-px py-2 pr-2 font-normal">
                <span className="sr-only">Selected</span>
              </th>
              <SortHeading label={npcColumns ? "NPC" : "Character"} by="character" sort={sort} onSort={sortBy} />
              {npcColumns ? (
                <>
                  <SortHeading label="Kind" by="kind" sort={sort} onSort={sortBy} className={WIDE} />
                  <SortHeading label="Form" by="form" sort={sort} onSort={sortBy} className={WIDE} />
                  <SortHeading label="Rating" by="rating" sort={sort} onSort={sortBy} className={WIDE} />
                  <SortHeading label="On the Who’s Who" by="listed" sort={sort} onSort={sortBy} className={WIDE} />
                </>
              ) : (
                <>
                  <SortHeading label="Player" by="player" sort={sort} onSort={sortBy} className={WIDE} />
                  <SortHeading label="Clan" by="clan" sort={sort} onSort={sortBy} className={WIDE} />
                  <SortHeading label="Age" by="age" sort={sort} onSort={sortBy} className={WIDE} />
                  <th className={`${WIDE} py-2 pr-3 font-normal`}>Here as</th>
                  <th className={`${WIDE} py-2 pr-3 font-normal`}>Flags</th>
                </>
              )}
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
                npcColumns={npcColumns}
                staffing={staffing}
                selected={selected.has(entry.character_id)}
                onSelect={() => toggle(entry.character_id)}
                values={valueColumns.map((c) => [c.label, valueOf(entry, c.key)])}
                equipment={showEquipment ? (matched?.get(entry.character_id)?.equipment ?? []) : null}
              />
            ))}
          </tbody>
        </table>
      )}
      {show === "npcs" && npcsInShow.length > 0 && <p className="mt-3 text-xs text-mist">NPCs with a title here are on the Who’s Who. List one without from its ⋯.</p>}
    </Card>
  );
}

/** Player characters, NPCs or everyone, side by side: the list's first choice. */
function ShowChoice({ show, onChange }: { show: Show; onChange: (show: Show) => void }) {
  return (
    <span role="radiogroup" aria-label="Show" className="inline-flex overflow-hidden rounded-md border border-ash">
      {(["pcs", "npcs", "everyone"] as const).map((s) => (
        <button
          key={s}
          type="button"
          role="radio"
          aria-checked={show === s}
          onClick={() => onChange(s)}
          className={`min-h-10 px-2.5 text-sm sm:px-3 ${show === s ? "bg-gold/20 text-gold" : "text-mist hover:text-parchment"} [&+&]:border-l [&+&]:border-ash`}
        >
          {SHOW_NAMES[s][0]}
        </button>
      ))}
    </span>
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
 * stands here, what needs staff (or, among NPCs alone, an NPC's kind, form, rating
 * and listing), the numbers the filter compares, and what staff do for it behind ⋯
 * (StaffActions). */
function RosterRow({
  troupeId,
  entry,
  npcColumns,
  staffing,
  selected,
  onSelect,
  values,
  equipment,
}: {
  troupeId: string;
  entry: RosterEntry;
  /** The NPCs' own columns in place of the player, clan, age and flags. */
  npcColumns: boolean;
  staffing: Staffing;
  selected: boolean;
  onSelect: () => void;
  /** The numbers the filter compares, such as ["Occult", 2]. */
  values: [string, number][];
  /** With a filter on equipment, the items it asks about that the character holds; null without one. */
  equipment: string[] | null;
}) {
  const named = useClanName();
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
  const kind = entry.npc_kind_name ?? entry.splat;
  const form = FORM_NAMES[(entry.npc_form ?? "sheeted") as NpcForm];
  const listed = entry.on_whos_who;
  // A Stock NPC's builder stands in for a sheet (issue #215).
  const to = entry.npc_form === "stock" ? `/troupes/${troupeId}/npcs/${entry.character_id}` : `/characters/${entry.character_id}`;
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
              <Link to={to} className="font-medium break-words hover:text-gold">
                {name}
              </Link>
              <Pronouns pronouns={entry.pronouns} />
              {entry.claim_expires_at && <Badge>Claim link out</Badge>}
            </span>
            {!npcColumns && entry.player_id && (
              <span className="lg:hidden">
                <PlayerLink entry={entry} />
              </span>
            )}
            {/* What the wide columns show, folded under the name. */}
            {npcColumns ? (
              <span className="flex flex-wrap items-center gap-1 text-xs text-mist lg:hidden">
                <Badge tone="gold">{kind}</Badge>
                <Badge>{form}</Badge>
                {entry.stock_rating != null && <Badge>Rating {entry.stock_rating}</Badge>}
                {listed && <span>On the Who’s Who</span>}
              </span>
            ) : (
              <>
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
              </>
            )}
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
      {npcColumns ? (
        <>
          <td className={`${WIDE} py-2.5 pr-3 align-top`}>
            <Badge tone="gold">{kind}</Badge>
          </td>
          <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{form}</td>
          <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{entry.stock_rating ?? <span aria-label="None">–</span>}</td>
          <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{listed ? "Yes" : "No"}</td>
        </>
      ) : (
        <>
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
        </>
      )}
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
        {/* Its dialogs sit here too, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
        <StaffActions troupeId={troupeId} entry={entry} staffing={staffing} />
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
