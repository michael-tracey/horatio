import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { EquipmentItemOut, EquipmentOut, EquipmentHolderOut } from "../../api/types";
import { EmptyState, showFilters } from "../../components/EmptyState";
import { InfoButton } from "../../components/InfoButton";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { ItemActions } from "../character/ItemActions";
import { EquipmentEditor, useEquipmentRules, useTroupeTemplates } from "./EquipmentEditor";
import { factsText, givenText, kindText, qualityText, type Kind } from "./equipment";
import { itemsCsv, readSearch, searchQuery, STATUS_NAMES, writeSearch, type ItemSearch, type Sort, type Status } from "./equipmentSearch";
import { charactersFilter, encode } from "./filters";

const KINDS: { key: Kind; name: string }[] = [
  { key: "melee", name: "Melee weapons" },
  { key: "ranged", name: "Ranged weapons" },
  { key: "protective", name: "Protective gear" },
  { key: "miscellaneous", name: "Miscellaneous gear" },
  { key: "text", name: "Vampiric texts" },
];
const GRADES = [
  { key: "cheap", name: "Cheap" },
  { key: "standard", name: "Standard" },
  { key: "special", name: "Special" },
];
const SORT_NAMES: Record<Sort, string> = { holder: "Holder", name: "Name", date: "Date given, newest first" };

// The results' columns, a table from a small tablet up; cards on a phone.
const COLUMNS = "sm:grid sm:grid-cols-[minmax(0,1.5fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.6fr)_4.5rem_minmax(0,1.2fr)] sm:gap-3";

/**
 * Every item the troupe's home characters hold, for its storytellers and
 * assistants: give one, change it, move it to another home character, discard it
 * or take it back. A search finds items by words in them, holder, kind, quality,
 * grade, who gave them and when, held or discarded (kept in the URL); each opens
 * with its history, the list exports as a CSV, and Find these characters opens
 * the Characters list on their holders. Items go with a character whose home
 * troupe changes.
 */
export function EquipmentTab({ troupeId, troupeName }: { troupeId: string; troupeName: string }) {
  const dates = useDates();
  const [params, setParams] = useSearchParams();
  const search = readSearch(params);
  const update = (change: Partial<ItemSearch>) => setParams(writeSearch({ ...search, ...change }), { replace: true });
  const [giving, setGiving] = useState(false);
  const [given, setGiven] = useState("");
  const query = searchQuery(search, (day) => dates.fromInput(`${day}T00:00`));
  const list = useQuery({
    queryKey: ["troupe-equipment", troupeId, query],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/equipment", { params: { path: { troupe_id: troupeId }, query } })),
    placeholderData: (previous) => previous,
  });
  const rules = useEquipmentRules("vampire");
  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const { items, characters, givers, not_shown } = list.data;
  // Nothing ever given here (held, taken back, discarded or a retired character's), and no search set: nothing to find yet.
  const ever = items.length + givers.length + Object.values(not_shown).reduce((sum, n) => sum + n, 0);
  const none = !showFilters(ever, writeSearch(search).toString() !== "");

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Equipment"
        info={
          <InfoButton label="About equipment">
            Only a character's home troupe gives it equipment or changes what it holds, and an item goes with its character wherever its home is. Weapons,
            protective gear and other gear, with the book's qualities (MET: VTM pp. 515–524), and Vampiric Texts.
          </InfoButton>
        }
        actions={
          !giving && (
            <Button
              variant="secondary"
              onClick={() => {
                setGiving(true);
                setGiven("");
              }}
            >
              Give equipment
            </Button>
          )
        }
      >
        {none && !giving ? (
          <EmptyState title="No equipment yet.">What {troupeName}'s home characters hold, PCs and NPCs, shows here. Start with Give equipment, above.</EmptyState>
        ) : (
          <p className="mb-3 text-sm text-mist">What {troupeName}'s home characters hold, PCs and NPCs.</p>
        )}
        {giving && (
          <EquipmentEditor
            troupeId={troupeId}
            troupeName={troupeName}
            holders={characters}
            onDone={(name) => {
              setGiving(false);
              setGiven(name);
            }}
          />
        )}
        {given && <Notice>Given {given}.</Notice>}
      </Card>
      {!none && <SearchForm search={search} update={update} rules={rules.data} holders={holderChoices(characters, items)} givers={givers} />}
      {!none && <Results troupeId={troupeId} troupeName={troupeName} search={search} update={update} items={items} notShown={not_shown} rules={rules.data} holders={characters} />}
      <TroupeTemplates troupeId={troupeId} troupeName={troupeName} rules={rules.data} />
    </div>
  );
}

/** The characters to search by: the troupe's home characters, and any other holder found (a retired one). */
function holderChoices(characters: EquipmentHolderOut[], items: EquipmentItemOut[]): { id: string; name: string }[] {
  const found = new Map(characters.map((c) => [c.id, c.name]));
  for (const i of items) if (!found.has(i.character_id)) found.set(i.character_id, i.character_name);
  return [...found].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
}

function SearchForm({
  search,
  update,
  rules,
  holders,
  givers,
}: {
  search: ItemSearch;
  update: (change: Partial<ItemSearch>) => void;
  rules: EquipmentOut | undefined;
  holders: { id: string; name: string }[];
  givers: { id: string; name: string }[];
}) {
  // Typing waits a moment before it searches.
  const [words, setWords] = useState(search.q);
  useEffect(() => {
    if (words === search.q) return;
    const wait = setTimeout(() => update({ q: words }), 300);
    return () => clearTimeout(wait);
  });
  const qualities = [...new Set((rules?.qualities ?? []).filter((q) => !search.kind || q.kind === search.kind).map((q) => q.name))].sort((a, b) => a.localeCompare(b));
  const nameOf = (id: string) => holders.find((h) => h.id === id)?.name ?? "another character";
  const toggle = (status: Status, on: boolean) => {
    const statuses = on ? [...search.statuses, status] : search.statuses.filter((s) => s !== status);
    update({ statuses: statuses.length ? statuses : ["held"] });
  };
  const narrow = "min-w-40 flex-1 sm:max-w-56 sm:flex-none";
  return (
    <Card title="Find items">
      <div className="flex flex-col gap-3">
        <Input
          type="search"
          aria-label="Search equipment"
          placeholder="Name, quality, special effect, description or staff note…"
          value={words}
          onChange={(e) => setWords(e.target.value)}
        />
        <div className="flex flex-wrap gap-3">
          <div className={narrow}>
            <Field label="Held by">
              <Select value="" onChange={(e) => e.target.value && update({ holders: [...search.holders, e.target.value] })}>
                <option value="">{search.holders.length ? "And…" : "Every character"}</option>
                {holders
                  .filter((h) => !search.holders.includes(h.id))
                  .map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name}
                    </option>
                  ))}
              </Select>
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Kind">
              <Select
                value={search.kind}
                onChange={(e) => {
                  const kind = e.target.value;
                  const keeps = !kind || (rules?.qualities ?? []).some((q) => q.kind === kind && q.name === search.quality);
                  update({ kind, ...(keeps ? {} : { quality: "" }) });
                }}
              >
                <option value="">Every kind</option>
                {KINDS.map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Quality">
              <Select value={search.quality} onChange={(e) => update({ quality: e.target.value })}>
                <option value="">Any quality</option>
                {qualities.map((q) => (
                  <option key={q}>{q}</option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Grade">
              <Select value={search.grade} onChange={(e) => update({ grade: e.target.value })}>
                <option value="">Any grade</option>
                {GRADES.map((g) => (
                  <option key={g.key} value={g.key}>
                    {g.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Given by">
              <Select value={search.givenBy} onChange={(e) => update({ givenBy: e.target.value })}>
                <option value="">Anyone</option>
                {givers.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Given from">
              <Input type="date" value={search.from} onChange={(e) => update({ from: e.target.value })} />
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Given until">
              <Input type="date" value={search.to} onChange={(e) => update({ to: e.target.value })} />
            </Field>
          </div>
          <div className={narrow}>
            <Field label="Sort by">
              <Select value={search.sort} onChange={(e) => update({ sort: e.target.value as Sort })}>
                {Object.entries(SORT_NAMES).map(([key, name]) => (
                  <option key={key} value={key}>
                    {name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
        {search.holders.length > 0 && (
          <ul aria-label="Holders searched" className="flex flex-wrap gap-2">
            {search.holders.map((id) => (
              <li key={id} className="inline-flex h-8 items-center gap-1 rounded-full border border-gold/50 px-2 text-xs text-gold">
                {nameOf(id)}
                <button type="button" aria-label={`Remove ${nameOf(id)}`} className="text-mist hover:text-parchment" onClick={() => update({ holders: search.holders.filter((h) => h !== id) })}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <legend className="sr-only">Which items</legend>
          {(Object.keys(STATUS_NAMES) as Status[]).map((status) => (
            <label key={status} className="flex items-center gap-1.5">
              <input type="checkbox" checked={search.statuses.includes(status)} onChange={(e) => toggle(status, e.target.checked)} />
              {STATUS_NAMES[status]}
            </label>
          ))}
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={search.retired} onChange={(e) => update({ retired: e.target.checked })} />
            Held by retired characters
          </label>
        </fieldset>
      </div>
    </Card>
  );
}

/** What is found: a table from a small tablet up, cards on a phone, each opening with its details and history. */
function Results({
  troupeId,
  troupeName,
  search,
  update,
  items,
  notShown,
  rules,
  holders,
}: {
  troupeId: string;
  troupeName: string;
  search: ItemSearch;
  update: (change: Partial<ItemSearch>) => void;
  items: EquipmentItemOut[];
  notShown: Record<string, number>;
  rules: EquipmentOut | undefined;
  holders: EquipmentHolderOut[];
}) {
  const dates = useDates();
  const searching = writeSearch(search).toString() !== "";
  const hidden = (Object.keys(notShown) as Status[]).filter((s) => notShown[s]);
  const owners = [...new Set(items.map((i) => i.character_id))];
  const exportCsv = () => {
    const csv = itemsCsv(items, (at) => dates.toInput(at).slice(0, 10));
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    link.download = `${troupeName} equipment.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return (
    <section aria-label="Equipment found" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="text-mist">{items.length === 1 ? "1 item" : `${items.length} items`}</span>
        {items.length > 0 && (
          <>
            <Button variant="secondary" className="min-h-8" onClick={exportCsv}>
              Export CSV
            </Button>
            <Link to={`/troupes/${troupeId}/characters?${new URLSearchParams({ filter: encode(charactersFilter(owners)) })}`} className="text-gold underline hover:text-parchment">
              Find these characters
            </Link>
          </>
        )}
        {hidden.length > 0 && (
          <span className="text-mist">
            · {hidden.map((s) => `${notShown[s]} ${STATUS_NAMES[s].toLowerCase()}`).join(" and ")} not shown{" "}
            <button type="button" className="underline hover:text-parchment" onClick={() => update({ statuses: [...search.statuses, ...hidden] })}>
              Show {hidden.length === 1 && notShown[hidden[0]!] === 1 ? "it" : "them"}
            </button>
          </span>
        )}
      </div>
      {items.length === 0 ? (
        <Empty>{searching ? "No equipment matches." : "No equipment yet."}</Empty>
      ) : (
        <div className="rounded-md border border-ash bg-dusk">
          <div aria-hidden="true" className={`hidden border-b border-ash px-3 py-2 text-xs text-mist ${COLUMNS}`}>
            <span>Item</span>
            <span>Held by</span>
            <span>Kind</span>
            <span>Qualities</span>
            <span>Grade</span>
            <span>Given</span>
          </div>
          <ul aria-label="Equipment" className="divide-y divide-ash">
            {items.map((item) => (
              <ItemRow key={item.id} item={item} rules={rules} troupeId={troupeId} troupeName={troupeName} holders={holders} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** One item: what it is, who holds it and where it came from, opening with what it does, staff's changes and its history. */
function ItemRow({
  item,
  rules,
  troupeId,
  troupeName,
  holders,
}: {
  item: EquipmentItemOut;
  rules: EquipmentOut | undefined;
  troupeId: string;
  troupeName: string;
  holders: EquipmentHolderOut[];
}) {
  const dates = useDates();
  const [open, setOpen] = useState(false);
  const label = `${item.name}, held by ${item.character_name}`;
  return (
    <li aria-label={label} className="p-3 text-sm">
      <div className={`flex flex-col gap-0.5 ${COLUMNS}`}>
        <span className="flex flex-wrap items-baseline gap-2">
          <button type="button" aria-expanded={open} aria-label={label} className="text-left font-medium text-gold hover:underline" onClick={() => setOpen(!open)}>
            {item.name}
          </button>
          {item.status !== "held" && <Badge tone="blood">{STATUS_NAMES[item.status]}</Badge>}
        </span>
        <span className="min-w-0">
          <span className="text-mist sm:hidden">{item.status === "held" ? "held by " : "last held by "}</span>
          <Link to={`/characters/${item.character_id}`} className="hover:text-gold">
            {item.character_name}
          </Link>
          <span className="text-xs text-mist">{item.character_kind === "npc" ? " (NPC)" : item.player_name ? ` (${item.player_name})` : ""}</span>
        </span>
        <span>{item.kind_name}</span>
        <span className={item.qualities.length ? "" : "text-mist"}>{item.qualities.length ? item.qualities.map(qualityText).join(", ") : "No qualities"}</span>
        <span>
          {item.grade.charAt(0).toUpperCase() + item.grade.slice(1)}
          <span className="sm:hidden"> grade</span>
        </span>
        <span className="text-xs text-mist">
          {dates.date(item.given_at)}
          {item.from_sheet ? ", from the sheet" : `, by ${item.given_by_name ?? "someone"}`}
          {!item.from_sheet && item.troupe_name !== troupeName && ` of ${item.troupe_name}`}
        </span>
      </div>
      {open && <ItemDetails item={item} rules={rules} troupeId={troupeId} troupeName={troupeName} holders={holders} />}
    </li>
  );
}

/** What an item does, and staff's changes to it. */
function ItemDetails({
  item,
  rules,
  troupeId,
  troupeName,
  holders,
}: {
  item: EquipmentItemOut;
  rules: EquipmentOut | undefined;
  troupeId: string;
  troupeName: string;
  holders: EquipmentHolderOut[];
}) {
  const dates = useDates();
  const [doing, setDoing] = useState<"" | "change" | "take" | "history">("");
  const facts = factsText(item.facts);
  const path = { character_id: item.character_id, item_id: item.id };
  const give = useAction(({ to, note }: { to: string; note: string }) =>
    unwrap(api.POST("/api/characters/{character_id}/equipment/{item_id}/give", { params: { path }, body: { to_character_id: to, note } })),
  );
  const discard = useAction((note: string) => unwrap(api.POST("/api/characters/{character_id}/equipment/{item_id}/discard", { params: { path }, body: { note } })));
  const restore = useAction(() =>
    unwrap(api.POST("/api/troupes/{troupe_id}/equipment/{item_id}/restore", { params: { path: { troupe_id: troupeId, item_id: item.id } } })),
  );
  const history = (
    <Button variant="ghost" aria-expanded={doing === "history"} onClick={() => setDoing(doing === "history" ? "" : "history")}>
      History
    </Button>
  );
  return (
    <div className="mt-2 rounded-md border border-ash/60 bg-night/40 p-3">
      {item.special && (
        <p className="mb-1">
          <Badge tone="gold">Special, by {item.special_troupe_name}</Badge>
        </p>
      )}
      <p>
        {kindText(rules, item)}
        {item.qualities.length > 0 && `: ${item.qualities.map(qualityText).join(", ")}`}
      </p>
      {facts && <p className="text-xs text-mist">{facts}</p>}
      {item.facts.aggravated_against.length > 0 && <p className="text-xs text-mist">Aggravated damage to {item.facts.aggravated_against.join("; ")}.</p>}
      {item.effects.length > 0 && (
        <ul aria-label={`${item.name}'s special effects`} className="mt-1 flex flex-col gap-0.5">
          {item.effects.map((e) => (
            <li key={e.name}>
              <span className="text-gold" title={`${item.special_troupe_name}'s own`}>
                ★ {e.name}
              </span>
              : {e.effect}
            </li>
          ))}
        </ul>
      )}
      {item.description && <p className="mt-1 whitespace-pre-line">{item.description}</p>}
      {item.staff_note && <p className="mt-1 whitespace-pre-line text-xs text-mist">Staff note: {item.staff_note}</p>}
      <p className="mt-1 text-xs text-mist">
        {givenText(item)}, {dates.date(item.given_at)}
      </p>
      {item.discarded && (
        <p className="mt-1 text-sm">
          Discarded by {item.discarded.by_name ?? "someone"}, {dates.date(item.discarded.at)}
          {item.discarded.note ? `: ${item.discarded.note}` : "."}
        </p>
      )}
      {item.status === "discarded" && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={restore.isPending} onClick={() => restore.mutate(undefined)}>
            Restore to {item.character_name}
          </Button>
          {history}
        </div>
      )}
      <ErrorText error={restore.error} />
      {item.can_change && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setDoing(doing === "change" ? "" : "change")}>
            Change
          </Button>
          <Button variant="secondary" onClick={() => setDoing(doing === "take" ? "" : "take")}>
            Take back
          </Button>
          {history}
        </div>
      )}
      {item.status === "taken_back" && <div className="mt-2">{history}</div>}
      {item.can_change && (
        <div className="mt-2">
          <ItemActions
            item={item}
            receivers={holders.filter((h) => h.id !== item.character_id).map((h) => ({ ...h, title: "" }))}
            give={(to, note) => give.mutateAsync({ to: to.id, note })}
            discard={(note) => discard.mutateAsync(note)}
          />
        </div>
      )}
      {doing === "change" && (
        <div className="mt-3">
          <EquipmentEditor troupeId={troupeId} troupeName={troupeName} holders={holders} item={item} onDone={() => setDoing("")} />
        </div>
      )}
      {doing === "take" && <TakeBack troupeId={troupeId} item={item} onDone={() => setDoing("")} />}
      {doing === "history" && <History troupeId={troupeId} item={item} />}
    </div>
  );
}

function TakeBack({ troupeId, item, onDone }: { troupeId: string; item: EquipmentItemOut; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const take = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/equipment/{item_id}/take-back", {
        params: { path: { troupe_id: troupeId, item_id: item.id } },
        body: { reason },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Take back ${item.name}`}
      className="mt-3 flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        take.mutate(undefined);
      }}
    >
      <Field label="Why it is taken back" hint={`${item.character_name}'s player is told, and it goes in the character's log.`}>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={take.error} />
      <div className="flex gap-2">
        <Button type="submit" variant="danger" disabled={take.isPending || !reason.trim()}>
          Take back {item.name}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function History({ troupeId, item }: { troupeId: string; item: EquipmentItemOut }) {
  const dates = useDates();
  const detail = useQuery({
    queryKey: ["equipment-item", item.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/equipment/{item_id}", { params: { path: { troupe_id: troupeId, item_id: item.id } } })),
  });
  if (detail.isPending) return <Loading />;
  if (detail.error) return <ErrorText error={detail.error} />;
  return (
    <ol aria-label={`${item.name}'s history`} className="mt-3 flex flex-col gap-1 border-l border-ash pl-3 text-xs">
      {detail.data.history.map((e) => (
        <li key={e.id}>
          <span className="text-mist">
            {dates.dateTime(e.at)}
            {e.actor_name && `, ${e.actor_name}`}:
          </span>{" "}
          {e.summary}
          {e.reason && ` (${e.reason})`}
        </li>
      ))}
    </ol>
  );
}

/** The troupe's own templates, to start items from; saved from the editor. */
function TroupeTemplates({ troupeId, troupeName, rules }: { troupeId: string; troupeName: string; rules: EquipmentOut | undefined }) {
  const templates = useTroupeTemplates(troupeId);
  const remove = useAction((templateId: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/equipment/templates/{template_id}", { params: { path: { troupe_id: troupeId, template_id: templateId } } })),
  );
  if (!templates.data?.length) return null;
  return (
    <Card title={`${troupeName}'s templates`}>
      <p className="mb-2 text-sm text-mist">Items to start from when giving equipment, beside the book's. Save one from the editor with Save as a template.</p>
      <ErrorText error={remove.error} />
      <ul className="flex flex-col gap-1 text-sm">
        {templates.data.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {t.name} <span className="text-mist">· {kindText(rules, t)}{t.qualities.length > 0 && `: ${t.qualities.map(qualityText).join(", ")}`}</span>
            </span>
            <Button variant="ghost" aria-label={`Delete the template ${t.name}`} disabled={remove.isPending} onClick={() => remove.mutate(t.id)}>
              Delete
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
