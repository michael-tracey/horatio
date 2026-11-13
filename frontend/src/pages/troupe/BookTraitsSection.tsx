import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BookTraitOut, CategoryOut, TraitOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { Explainer } from "../../components/Explainer";
import { RowEditor, useRowEditor } from "../../components/RowEditor";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { HouseWording } from "../../components/TroupeChange";
import { useRulesAction } from "../../hooks";
import { bookSummary } from "../../houseWording";
import { pageText } from "./bookPage";
import { bookTraits, changeSummary, findTraits, kindChoices, requirementNote, SHOWN } from "./bookTraits";
import { useHouseSplat } from "./HouseSplat";
import { useCatalogue } from "../../catalogue";

/** The trait whose panel is open, and the row it opened from: a change listed, or a trait found. */
type Picked = { splat: string; category: string; name: string; from: "changed" | "found" };
const samePick = (a: Picked, b: Picked) => a.splat === b.splat && a.category === b.category && a.name === b.name && a.from === b.from;

/**
 * Customise › House rules › Book traits: the troupe's own changes to traits from the book.
 * Storytellers search or browse the catalogue, open a trait, and change it in one
 * panel, under the row they opened it from: ban it, with a reason the players see, give it wording of the troupe's
 * own, and move a merit or flaw to another category. Those who already hold a banned trait keep it; they are listed here for
 * staff to deal with one by one.
 */
export function BookTraitsSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const { splat, picker } = useHouseSplat(troupeId);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const editor = useRowEditor<Picked>(samePick);
  // The row the panel was opened from, and where it was in its list: kept there while the panel is
  // open, though saving moves it (a trait found comes first once changed) or takes it away.
  const [opened, setOpened] = useState<{ row: BookTraitOut | TraitOut; at: number } | null>(null);
  const catalogue = useCatalogue(splat, troupeId);
  const changes = useQuery({
    queryKey: ["book-traits", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/book-traits", { params: { path: { troupe_id: troupeId } } })),
  });
  if (catalogue.isPending || changes.isPending) return <Loading />;
  if (catalogue.error || changes.error) return <ErrorText error={catalogue.error ?? changes.error} />;

  const categories = catalogue.data.categories.filter((c) => !c.derived);
  const traits = bookTraits(catalogue.data.traits, categories);
  const found = query.trim() || category ? findTraits(traits, query, category) : [];
  const changed = changes.data.changes.filter((c) => c.splat === splat);
  const pick = (t: { category: string; name: string }, from: Picked["from"]): Picked => ({ splat, category: t.category, name: t.name, from });
  const openFrom = (from: Picked["from"]) => (editor.open?.from === from && editor.open.splat === splat ? opened : null);
  const rows = keepInPlace(changed, openFrom("changed") as { row: BookTraitOut; at: number } | null, sameTrait, undone);
  const shown = keepInPlace(found.slice(0, SHOWN), openFrom("found") as { row: TraitOut; at: number } | null, sameTrait);
  const toggle = (row: BookTraitOut | TraitOut, at: number, from: Picked["from"], button: HTMLElement) => {
    setOpened({ row, at });
    editor.toggle(pick(row, from), button);
  };
  const panel = (t: { category: string; name: string }) => {
    const trait = traits.find((x) => x.category === t.category && x.name === t.name);
    return (
      trait && (
        <RowEditor className="pt-1 pb-3">
          <TraitPanel
            troupeId={troupeId}
            splat={splat}
            trait={trait}
            categories={categories}
            kinds={kindChoices(changes.data.kinds ?? {}, splat, trait.category)}
            canEdit={canEdit}
            onClose={editor.close}
          />
        </RowEditor>
      )
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {picker}
      <Explainer id="rules-book-traits" title="How book trait changes work">
        <p className="text-sm">
          Change a trait from the book for this troupe. A banned trait can't be bought or picked by characters whose home troupe this is, or who are
          being built for it, at creation or after. It shows greyed out in their lists with your reason.
        </p>
        <p className="mt-2 text-sm text-mist">
          Characters who already hold it keep it. Their sheet lists it under “Against the rules”, and they are listed below so you can deal with each
          one. An exception can still let one character have it.
        </p>
      </Explainer>

      <Card title="Changed in this troupe">
        {rows.length === 0 ? (
          <EmptyState title="No book traits changed yet.">Every trait plays as the book has it. Find one below to change it.</EmptyState>
        ) : (
          <ul className="divide-y divide-ash">
            {rows.map((c, at) => {
              const open = editor.isOpen(pick(c, "changed"));
              return (
                <li key={`${c.category}/${c.name}`}>
                  <ChangeRow change={c} open={open} onToggle={(button) => toggle(c, at, "changed", button)} />
                  {open && panel(c)}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {changes.data.holders.length > 0 && (
        <Card title="Characters holding a banned trait">
          <p className="mb-2 text-sm text-mist">Nothing on their sheets changes by itself. Talk to each player, or give an exception.</p>
          <ul className="divide-y divide-ash">
            {changes.data.holders.map((h) => (
              <li key={`${h.character_id}/${h.category}/${h.name}/${h.detail}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <Link to={`/characters/${h.character_id}`} className="text-parchment underline hover:text-gold">
                  {h.character_name}
                </Link>
                <span className="text-mist">
                  {h.name}
                  {h.detail && `: ${h.detail}`}
                </span>
                {h.excepted && <Badge tone="gold">By exception</Badge>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Find a book trait">
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            type="search"
            aria-label="Search book traits"
            placeholder={`Search ${traits.length} traits…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-0 flex-1"
            ref={editor.fallback}
          />
          <Select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="sm:w-56">
            <option value="">Every category</option>
            {categories.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
        {(query.trim() || category) &&
          (found.length === 0 ? (
            <p className="mt-3 text-sm text-mist">No traits match.</p>
          ) : (
            <>
              <ul className="mt-3 divide-y divide-ash" aria-label="Book traits found">
                {shown.map((t, at) => {
                  const open = editor.isOpen(pick(t, "found"));
                  return (
                    <li key={`${t.category}/${t.name}`}>
                      <button
                        type="button"
                        aria-expanded={open}
                        onClick={(e) => toggle(t, at, "found", e.currentTarget)}
                        className={`flex min-h-10 w-full flex-wrap items-center gap-x-2 py-1.5 text-left text-sm hover:text-gold ${open ? "text-gold" : ""}`}
                      >
                        <span className={open ? "text-gold" : "text-parchment"}>{t.name}</span>
                        <span className="text-xs text-mist">{categoryName(categories, t.category)}</span>
                        {t.changed?.banned && <Badge tone="blood">Banned</Badge>}
                        {t.changed?.wording && <Badge tone="gold">House wording</Badge>}
                        {t.changed?.kind && <Badge tone="gold">{t.changed.kind}</Badge>}
                        <span className="ml-auto text-xs text-mist" aria-hidden="true">
                          {open ? "Close" : "Open"}
                        </span>
                      </button>
                      {open && panel(t)}
                    </li>
                  );
                })}
              </ul>
              {found.length > SHOWN && <p className="mt-2 text-xs text-mist">Showing {SHOWN} of {found.length}. Type more to narrow it.</p>}
            </>
          ))}
      </Card>
    </div>
  );
}

const categoryName = (categories: CategoryOut[], key: string) => categories.find((c) => c.key === key)?.name ?? key;

const sameTrait = (a: { category: string; name: string }, b: { category: string; name: string }) => a.category === b.category && a.name === b.name;

/** A change saving has undone: the trait plays as the book has it again. */
const undone = (c: BookTraitOut): BookTraitOut => ({ ...c, banned: false, ban_reason: "", wording: "", kind: null });

/**
 * A list as it is now, with the row whose panel is open kept where it was when it
 * opened, so the panel doesn't jump away: saving can move a trait found (a changed
 * one comes first), or take a change from the list. A row gone from the list comes
 * back as `gone` makes it, or, with no `gone`, stays gone, and its panel with it.
 */
export function keepInPlace<T>(rows: T[], opened: { row: T; at: number } | null, same: (a: T, b: T) => boolean, gone?: (row: T) => T): T[] {
  if (!opened) return rows;
  const now = rows.find((r) => same(r, opened.row));
  if (!now && !gone) return rows;
  const rest = rows.filter((r) => !same(r, opened.row));
  const at = Math.min(opened.at, rest.length);
  return [...rest.slice(0, at), now ?? gone!(opened.row), ...rest.slice(at)];
}

function ChangeRow({ change, open, onToggle }: { change: BookTraitOut; open: boolean; onToggle: (button: HTMLElement) => void }) {
  return (
    <div className="flex flex-col gap-1 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-4">
      <span className="min-w-0 flex-1">
        <span className="text-parchment">{change.name}</span>
        <span className="text-mist">
          {" "}
          · {change.category_name}
          {change.page && ` ${pageText(change.page)}`}
        </span>
        {changeSummary(change).map((s) => (
          <span key={s} className="block text-xs text-mist">
            {s}
          </span>
        ))}
        {changeSummary(change).length === 0 && <span className="block text-xs text-mist">No changes now: it plays as the book has it.</span>}
      </span>
      <Button
        variant="secondary"
        className="self-start sm:self-center"
        onClick={(e) => onToggle(e.currentTarget)}
        aria-expanded={open}
        aria-label={`${open ? "Close" : "Open"} ${change.name}`}
      >
        {open ? "Close" : "Open"}
      </Button>
    </div>
  );
}

/** One trait's changes in this troupe, a control for each, saved together. */
function TraitPanel({
  troupeId,
  splat,
  trait,
  categories,
  kinds,
  canEdit,
  onClose,
}: {
  troupeId: string;
  splat: string;
  trait: TraitOut;
  categories: CategoryOut[];
  /** The categories a merit or flaw can be moved to; none for any other trait. */
  kinds: string[];
  canEdit: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const titleId = useId();
  const bookKind = trait.changed?.book_kind ?? trait.kind ?? null;
  const saved = {
    banned: trait.changed?.banned ?? false,
    ban_reason: trait.changed?.ban_reason ?? "",
    wording: trait.changed?.wording ?? "",
    wording_mode: trait.changed?.wording_mode ?? ("added" as const),
    kind: trait.changed?.kind ?? "",
  };
  // The checks about it, to show which stay with it whatever its category.
  const checks = useQuery({
    queryKey: ["checks", troupeId],
    enabled: kinds.length > 0,
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/checks", { params: { path: { troupe_id: troupeId } } })),
  });
  const own = (checks.data ?? []).filter((c) => c.category === trait.category && c.about === trait.name && !c.key.endsWith("/requirement"));
  const [draft, setDraft] = useState(saved);
  const set = (next: Partial<typeof draft>) => setDraft((d) => ({ ...d, ...next }));
  const save = useRulesAction((body: Omit<typeof draft, "kind"> & { kind?: string }) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/book-traits", {
        params: { path: { troupe_id: troupeId } },
        body: { splat, category: trait.category, name: trait.name, ...body },
      }),
    ),
  );
  const sent = { ...draft, ban_reason: draft.banned ? draft.ban_reason.trim() : "", wording: draft.wording.trim() };
  // Only a merit or flaw has a category to send.
  const body = kinds.length > 0 ? sent : { ...sent, kind: undefined };
  const dirty = (Object.keys(saved) as (keyof typeof saved)[]).some((k) => sent[k] !== saved[k]);
  return (
    <section aria-labelledby={titleId} className="rounded-md border border-gold/50 bg-night/30 p-3 sm:p-4">
      <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 id={titleId} className="text-gold">
          {trait.name}
        </h3>
        <Button variant="ghost" className="min-h-8 px-2" onClick={onClose}>
          Close
        </Button>
      </header>
      <p className="text-sm text-mist">
        {categoryName(categories, trait.category)}
        {trait.page_reference && ` · ${pageText(trait.page_reference)}`}
      </p>
      {trait.description && (
        <p className="mt-2 text-sm">
          <span className="text-xs text-mist">The book's summary: </span>
          {trait.description}
        </p>
      )}

      <section className="mt-4 flex flex-col gap-3 border-t border-ash pt-4" aria-label="Ban">
        <label className="flex min-h-10 items-center gap-3 text-sm">
          <input type="checkbox" checked={draft.banned} disabled={!canEdit} onChange={(e) => set({ banned: e.target.checked })} className="h-5 w-5" />
          <span>
            Banned in this troupe
            <span className="block text-xs text-mist">Characters can't buy or pick it. Those who hold it keep it, flagged on their sheet.</span>
          </span>
        </label>
        {draft.banned && (
          <Field label="Reason (optional)" hint="Players see this beside the trait.">
            <Textarea rows={2} maxLength={500} value={draft.ban_reason} disabled={!canEdit} onChange={(e) => set({ ban_reason: e.target.value })} />
          </Field>
        )}
      </section>

      <section className="mt-4 flex flex-col gap-3 border-t border-ash pt-4" aria-label="Wording">
        <Field label="House wording" hint="In Markdown. Write the troupe's own words: never copy the book's text. Leave it empty for none.">
          <Textarea rows={4} maxLength={4000} value={draft.wording} disabled={!canEdit} onChange={(e) => set({ wording: e.target.value })} />
        </Field>
        <fieldset className="flex flex-col gap-1 text-sm" disabled={!canEdit}>
          <legend className="mb-1 text-mist">How it reads</legend>
          {(
            [
              ["added", "Added to the book's summary"],
              ["replaces", "In place of the book's summary"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="flex min-h-8 items-center gap-2">
              <input type="radio" name={`wording-mode-${trait.name}`} checked={draft.wording_mode === value} onChange={() => set({ wording_mode: value })} />
              {label}
            </label>
          ))}
        </fieldset>
        {draft.wording.trim() && (
          <div className="rounded-md border border-ash bg-night/40 p-3 text-sm" aria-label="How players see it">
            <p className="mb-1 text-xs text-mist">How players see it</p>
            {bookSummary(trait.description, draft) && <p className="mb-1 text-mist">{trait.description}</p>}
            <HouseWording change={draft} />
          </div>
        )}
      </section>

      {kinds.length > 0 && bookKind && (
        <section className="mt-4 flex flex-col gap-3 border-t border-ash pt-4" aria-label="Category">
          <Field label="Category in this troupe" hint={`${bookKind} in the book. Every rule tied to the category follows: clan merit values, sect and type checks, filters.`}>
            <Select value={draft.kind} disabled={!canEdit} onChange={(e) => set({ kind: e.target.value === bookKind ? "" : e.target.value })}>
              <option value="">As the book has it ({bookKind})</option>
              {kinds
                .filter((k) => k !== bookKind)
                .map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
            </Select>
          </Field>
          {draft.kind && requirementNote(bookKind, draft.kind, trait.requirement) && (
            <p className="text-sm text-gold">{requirementNote(bookKind, draft.kind, trait.requirement)}</p>
          )}
          {draft.kind && (
            <div className="text-sm text-mist">
              {own.length > 0 ? (
                <>
                  <p>Its own checks stay, whatever its category; change them on the Checks page:</p>
                  <ul className="mt-1 list-disc pl-5">
                    {own.map((c) => (
                      <li key={c.key}>{c.message}</li>
                    ))}
                  </ul>
                </>
              ) : checks.isLoading ? (
                <Loading compact />
              ) : (
                <p>It has no checks of its own to keep.</p>
              )}
              <p className="mt-1">Characters who hold it keep it. A rule it newly breaks is flagged on their sheet, not enforced.</p>
            </div>
          )}
        </section>
      )}

      {canEdit && (
        <div className="mt-4 border-t border-ash pt-4">
          <Button
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(body, { onSuccess: () => toast({ message: `Saved: ${trait.name} in this troupe` }) })}
          >
            Save
          </Button>
        </div>
      )}
      <ErrorText error={save.error} />
    </section>
  );
}
