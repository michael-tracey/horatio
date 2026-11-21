import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, TitlesOut } from "../../api/types";
import { ActionMenu, MenuItem } from "../../components/ActionMenu";
import { Avatar } from "../../components/Avatar";
import { useClanName } from "../../components/ClanNames";
import { DataTable, type Column } from "../../components/DataTable";
import { Dialog } from "../../components/Dialog";
import { LinesVeilsNote } from "../../components/LinesVeils";
import { AtHandle } from "../../components/PersonPicker";
import { Pronouns } from "../../components/PronounsInput";
import { Badge, Button, Card, Empty, ErrorText, Input, Loading, Select } from "../../components/ui";
import { useWidePage } from "../../components/widePage";
import { useEquipmentRules } from "./EquipmentEditor";
import { holdersLink } from "./equipmentSearch";
import { FilterBuilder } from "./FilterBuilder";
import { asksEquipment, columnLabel, columnOf, columns, decode, DEFAULT_FILTER, encode, filterLabel, ready, sentence, type Group, type Names } from "./filters";
import { TroupeExport } from "../character/Backup";
import { NewNpc } from "./NewNpc";
import { FORM_NAMES, filterNpcs, kindsIn, type NpcFilter, type NpcForm } from "./npcKinds";
import { ageRank, clanText, nextSort, showOf, shows, sortRows, type Show, type Sort } from "./roster";
import { StaffActions, TitlePill, useStaffing } from "./StaffActions";
import type { Staffing } from "./staffActions";
import { useCatalogue } from "../../catalogue";
import { CardHeading } from "../../components/Headings";
import { SortHeading } from "../../components/SortHeading";

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
 * NPCs shown come their kind, form and Stock rating, and the way to make another. Its ⋯
 * exports them as a backup (#567); storytellers (`canEmail`) may add players' emails.
 * It also imports a troupe's export (TroupeImportPage).
 */
export function RosterTab({ troupeId, canEmail = false }: { troupeId: string; canEmail?: boolean }) {
  useWidePage();
  const path = { params: { path: { troupe_id: troupeId } } };
  const named = useClanName();
  const roster = useQuery({ queryKey: ["roster", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", path)) });
  const catalogue = useCatalogue("vampire", troupeId);
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
  const [exporting, setExporting] = useState(false);
  const [sort, setSort] = useState<Sort>(null);
  const staffing = useStaffing(troupeId);
  const navigate = useNavigate();
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;

  const everyone = roster.data;
  // Player characters, NPCs or both; then the NPCs' kind and form; then the sheet filter and the search.
  const inShow = everyone.filter((e) => shows(show, e.kind));
  const npcsInShow = inShow.filter((e) => e.kind === "npc");
  const byKind = withNpcs ? filterNpcs(inShow, npcFilter) : inShow;
  // Until the filter's first answer, the list stays as it is (but the retired, which
  // the opening filter hides) under a loader, never "No characters match" (#568). A
  // later change of filter keeps the last answer, dimmed, until the next comes.
  const waiting = sent.items.length > 0 && !search.data && !search.error;
  const matched = sent.items.length && !waiting ? new Map((search.data ?? []).map((m) => [m.character_id, m])) : null;
  const stale = waiting || (search.isPlaceholderData && search.isFetching);
  const hidesRetired = sent.match === "all" && sent.items.some((c) => JSON.stringify(c) === JSON.stringify(DEFAULT_FILTER.items[0]));
  const q = query.trim().toLowerCase();
  const shown = byKind.filter(
    (e) =>
      (matched ? matched.has(e.character_id) : !(waiting && hidesRetired && e.retired)) &&
      (!q || `${e.character_name} ${e.player_name} ${e.player_handle ?? ""}`.toLowerCase().includes(q)),
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
  // A column for each number the filter compares, such as Occult, to line them up:
  // once the search has said what they are.
  const valueColumns = matched ? columns(sent).map((c) => ({ label: columnLabel(c, names), key: columnOf(c)! })) : [];
  const valueOf = (e: RosterEntry, key: string) => matched?.get(e.character_id)?.values[key] ?? 0;
  const showEquipment = !!matched && asksEquipment(sent);
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
          <ActionMenu label="More for the troupe's characters">
            <MenuItem onSelect={() => setExporting(true)}>Export characters and NPCs…</MenuItem>
            <MenuItem onSelect={() => navigate(`/troupes/${troupeId}/roster/import`)}>Import characters and NPCs…</MenuItem>
          </ActionMenu>
          <Dialog title="Export characters and NPCs" open={exporting} onClose={() => setExporting(false)}>
            {exporting && <TroupeExport troupeId={troupeId} selected={ticked.filter((e) => e.home || e.kind === "npc").map((e) => e.character_id)} canEmail={canEmail} />}
          </Dialog>
        </span>
      }
    >
      {withNpcs && making && (
        <section aria-labelledby="new-npc" className="mb-3 rounded-md border border-ash p-3">
          <CardHeading id="new-npc" className="mb-2">
            New NPC
          </CardHeading>
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
          </span>
          {search.isFetching && <Loading compact label="Searching…" />}
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
      ) : shown.length === 0 && waiting ? (
        <Loading label="Searching…" />
      ) : shown.length === 0 ? (
        <Empty>{byKind.length === 0 ? "No NPCs of that kind." : "No characters match."}</Empty>
      ) : (
        <DataTable
          label={show === "npcs" ? "NPCs" : "Characters"}
          busy={stale}
          className={`transition-opacity ${stale ? "opacity-60" : ""}`}
          stackBelow="lg"
          // Lined up with the name, past the picture.
          foldClassName="pl-11"
          rows={rows}
          rowKey={(e) => e.character_id}
          columns={rosterColumns({
            troupeId,
            npcColumns,
            named,
            staffing,
            sort,
            onSort: sortBy,
            selected,
            onSelect: toggle,
            valueColumns,
            valueOf,
            equipmentOf: showEquipment ? (e) => matched?.get(e.character_id)?.equipment ?? [] : null,
          })}
        />
      )}
      <TitleKey entries={rows} />
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

/**
 * The roster's columns: who each character is and who plays it, its clan and social
 * age, how it stands here, what needs staff (or, among NPCs alone, an NPC's kind,
 * form, rating and listing), the numbers the filter compares, and what staff do for
 * it behind ⋯ (StaffActions). On a phone or a narrow window all but the tick box,
 * the name and the ⋯ fold in under the name (DataTable).
 */
function rosterColumns({
  troupeId,
  npcColumns,
  named,
  staffing,
  sort,
  onSort,
  selected,
  onSelect,
  valueColumns,
  valueOf,
  equipmentOf,
}: {
  troupeId: string;
  /** The NPCs' own columns in place of the player, clan, age and flags. */
  npcColumns: boolean;
  named: ReturnType<typeof useClanName>;
  staffing: Staffing;
  sort: Sort;
  onSort: (by: string) => void;
  selected: Set<string>;
  onSelect: (id: string) => void;
  /** The numbers the filter compares, such as Occult. */
  valueColumns: { label: string; key: string }[];
  valueOf: (e: RosterEntry, key: string) => number;
  /** With a filter on equipment, the items it asks about that a character holds; null without one. */
  equipmentOf: ((e: RosterEntry) => string[]) | null;
}): Column<RosterEntry>[] {
  const sorted = (label: string, by: string): Pick<Column<RosterEntry>, "header" | "label" | "sort"> => {
    const way = sort?.by === by ? (sort.descending ? "descending" : "ascending") : undefined;
    return { header: <SortHeading label={label} sort={way} onSort={() => onSort(by)} />, label, sort: way };
  };
  const clan = (e: RosterEntry) => clanText(named(e.clan), e.social_age);
  const represented = (e: RosterEntry) =>
    !e.seated && <span className="block text-xs text-mist">Represented by: {named(e.represented_by) ?? "nobody yet"}</span>;
  const held = (e: RosterEntry) => {
    const items = equipmentOf?.(e);
    return items?.length ? (
      <span className="text-xs text-gold/90">
        {items.join(" · ")}
      </span>
    ) : null;
  };
  const kind = (e: RosterEntry) => e.npc_kind_name ?? e.splat;
  // A group of Stock NPCs (#1056) says how many.
  const form = (e: RosterEntry) => FORM_NAMES[(e.npc_form ?? "sheeted") as NpcForm] + ((e.stock_count ?? 1) > 1 ? `, a group of ${e.stock_count}` : "");
  return [
    {
      key: "select",
      header: <span className="sr-only">Selected</span>,
      label: "Selected",
      phone: "always",
      className: "pr-2",
      cell: (e) => <input type="checkbox" aria-label={`Select ${e.character_name}`} checked={selected.has(e.character_id)} onChange={() => onSelect(e.character_id)} className="mt-2.5" />,
    },
    { key: "character", ...sorted(npcColumns ? "NPC" : "Character", "character"), phone: "title", cell: (e) => <CharacterCell troupeId={troupeId} entry={e} /> },
    ...(npcColumns
      ? ([
          { key: "kind", ...sorted("Kind", "kind"), phone: "shown", bare: true, cell: (e) => <Badge tone="gold">{kind(e)}</Badge> },
          { key: "form", ...sorted("Form", "form"), phone: "shown", className: "text-mist", cell: form },
          {
            key: "rating",
            ...sorted("Rating", "rating"),
            phone: "shown",
            className: "text-mist",
            cell: (e) => e.stock_rating ?? <span aria-label="None">–</span>,
            folded: (e) => e.stock_rating,
          },
          {
            key: "listed",
            ...sorted("On the Who’s Who", "listed"),
            phone: "shown",
            className: "text-mist",
            cell: (e) => (e.on_whos_who ? "Yes" : "No"),
            folded: (e) => (e.on_whos_who ? "Yes" : null),
          },
        ] satisfies Column<RosterEntry>[])
      : ([
          { key: "player", ...sorted("Player", "player"), phone: "shown", cell: (e) => e.player_id && <PlayerLink entry={e} /> },
          {
            key: "clan",
            ...sorted("Clan", "clan"),
            phone: "shown",
            className: "text-parchment/80",
            cell: (e) => (clan(e) || represented(e)) && (
              <>
                {clan(e) && <span>{clan(e)}</span>}
                {represented(e)}
              </>
            ),
          },
          { key: "age", ...sorted("Age", "age"), phone: "shown", className: "whitespace-nowrap text-parchment/80", cell: (e) => e.social_age },
          { key: "here", header: "Here as", phone: "shown", bare: true, cell: (e) => <HereAs entry={e} /> },
          { key: "flags", header: "Flags", phone: "shown", bare: true, cell: (e) => <Flags troupeId={troupeId} entry={e} />, folded: (e) => (hasFlags(e) ? <Flags troupeId={troupeId} entry={e} /> : null) },
        ] satisfies Column<RosterEntry>[])),
    ...valueColumns.map(
      (c): Column<RosterEntry> => ({ key: `value:${c.key}`, ...sorted(c.label, `value:${c.key}`), phone: "shown", numeric: true, cell: (e) => valueOf(e, c.key) }),
    ),
    ...(equipmentOf ? [{ key: "equipment", header: "Equipment asked about", phone: "shown", cell: held } satisfies Column<RosterEntry>] : []),
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      label: "Actions",
      phone: "always",
      className: "text-right",
      // Its dialogs sit here too, as nothing but cells may sit in a row (Dialog sets its own text-left).
      cell: (e) => <StaffActions troupeId={troupeId} entry={e} staffing={staffing} />,
    },
  ];
}

/** The character's picture and name, linking to its sheet, with its pronouns, the titles it holds here and its lines and veils. */
function CharacterCell({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const name = entry.character_name;
  // A Stock NPC's builder stands in for a sheet (issue #215).
  const to = entry.npc_form === "stock" ? `/troupes/${troupeId}/npcs/${entry.character_id}` : `/characters/${entry.character_id}`;
  return (
    <div className="flex items-start gap-2">
      <Avatar name={name} picture={entry.picture} clan={entry.clan} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <Link to={to} className="font-medium wrap-anywhere hover:text-gold">
            {name}
          </Link>
          <Pronouns pronouns={entry.pronouns} />
          {entry.claim_expires_at && <Badge>Claim link out</Badge>}
        </span>
        <HeldTitles entry={entry} />
        <LinesVeilsNote value={entry.lines_veils} who={entry.player_name} className="text-xs text-parchment/80" />
      </div>
    </div>
  );
}

/** How the character stands here: an NPC, at home, or visiting. */
function HereAs({ entry }: { entry: RosterEntry }) {
  return entry.kind === "npc" ? <Badge>NPC</Badge> : entry.home ? <Badge tone="gold">Home</Badge> : <Badge>Visiting</Badge>;
}

function hasFlags(entry: RosterEntry): boolean {
  return entry.player_suspended || entry.waiting || entry.backstory_waiting || entry.disciplines_waiting > 0;
}

/** What needs staff: a suspended player, a request to make this home, a backstory to read, disciplines to approve. */
function Flags({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  return (
    <span className="flex flex-wrap gap-1">
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
    </span>
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

/** What the title pills' star and red mean, under the list while one shown has them:
 * a hover title never shows on a phone. The Titles dialog on ⋯ says it for its one character. */
function TitleKey({ entries }: { entries: RosterEntry[] }) {
  const active = entries.some((e) => e.active_title && e.titles.includes(e.active_title));
  const outOfSect = entries.some((e) => e.titles.some((t) => e.out_of_sect_titles.includes(t)));
  if (!active && !outOfSect) return null;
  return (
    <p className="mt-3 text-xs text-mist">
      {active && <>★ marks a character&apos;s active title, the one that gives status.</>}
      {active && outOfSect && " "}
      {outOfSect && <>A title in red is out of the character&apos;s sect, kept until taken.</>}
    </p>
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
