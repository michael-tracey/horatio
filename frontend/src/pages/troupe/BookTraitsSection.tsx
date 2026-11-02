import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BookTraitOut, CategoryOut, TraitOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { Explainer } from "../../components/Explainer";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { HouseWording } from "../../components/TroupeChange";
import { useAction } from "../../hooks";
import { bookSummary } from "../../houseWording";
import { pageText } from "./bookPage";
import { bookTraits, changeSummary, findTraits, SHOWN } from "./bookTraits";
import { useHouseSplat } from "./HouseSplat";

type Picked = { category: string; name: string };

/**
 * Customise › Rules › Book traits: the troupe's own changes to traits from the book.
 * Storytellers search or browse the catalogue, open a trait, and change it in one
 * panel: ban it, with a reason the players see, and give it wording of the troupe's
 * own. Those who already hold a banned trait keep it; they are listed here for
 * staff to deal with one by one.
 */
export function BookTraitsSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const { splat, picker } = useHouseSplat(troupeId);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const catalogue = useQuery({
    queryKey: ["catalogue", splat, troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: { troupe_id: troupeId } } })),
  });
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
  const open = picked && traits.find((t) => t.category === picked.category && t.name === picked.name);

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

      {open && <TraitPanel key={`${splat}/${open.category}/${open.name}`} troupeId={troupeId} splat={splat} trait={open} categories={categories} canEdit={canEdit} onClose={() => setPicked(null)} />}

      <Card title="Changed in this troupe">
        {changed.length === 0 ? (
          <EmptyState title="No book traits changed yet.">Every trait plays as the book has it. Find one below to change it.</EmptyState>
        ) : (
          <ul className="divide-y divide-ash">
            {changed.map((c) => (
              <ChangeRow key={`${c.category}/${c.name}`} change={c} onOpen={() => setPicked(c)} />
            ))}
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
                {found.slice(0, SHOWN).map((t) => (
                  <li key={`${t.category}/${t.name}`}>
                    <button
                      type="button"
                      onClick={() => setPicked(t)}
                      className="flex min-h-10 w-full flex-wrap items-center gap-x-2 py-1.5 text-left text-sm hover:text-gold"
                    >
                      <span className="text-parchment">{t.name}</span>
                      <span className="text-xs text-mist">{categoryName(categories, t.category)}</span>
                      {t.changed?.banned && <Badge tone="blood">Banned</Badge>}
                      {t.changed?.wording && <Badge tone="gold">House wording</Badge>}
                    </button>
                  </li>
                ))}
              </ul>
              {found.length > SHOWN && <p className="mt-2 text-xs text-mist">Showing {SHOWN} of {found.length}. Type more to narrow it.</p>}
            </>
          ))}
      </Card>
    </div>
  );
}

const categoryName = (categories: CategoryOut[], key: string) => categories.find((c) => c.key === key)?.name ?? key;

function ChangeRow({ change, onOpen }: { change: BookTraitOut; onOpen: () => void }) {
  return (
    <li className="flex flex-col gap-1 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-4">
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
      </span>
      <Button variant="secondary" className="self-start" onClick={onOpen} aria-label={`Open ${change.name}`}>
        Open
      </Button>
    </li>
  );
}

/** One trait's changes in this troupe, a control for each, saved together. */
function TraitPanel({
  troupeId,
  splat,
  trait,
  categories,
  canEdit,
  onClose,
}: {
  troupeId: string;
  splat: string;
  trait: TraitOut;
  categories: CategoryOut[];
  canEdit: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const saved = {
    banned: trait.changed?.banned ?? false,
    ban_reason: trait.changed?.ban_reason ?? "",
    wording: trait.changed?.wording ?? "",
    wording_mode: trait.changed?.wording_mode ?? ("added" as const),
  };
  const [draft, setDraft] = useState(saved);
  const set = (next: Partial<typeof draft>) => setDraft((d) => ({ ...d, ...next }));
  const save = useAction((body: typeof draft) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/book-traits", {
        params: { path: { troupe_id: troupeId } },
        body: { splat, category: trait.category, name: trait.name, ...body },
      }),
    ),
  );
  const sent = { ...draft, ban_reason: draft.banned ? draft.ban_reason.trim() : "", wording: draft.wording.trim() };
  const dirty = (Object.keys(saved) as (keyof typeof saved)[]).some((k) => sent[k] !== saved[k]);
  return (
    <Card
      title={trait.name}
      actions={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
      className="border-gold/50"
    >
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

      {canEdit && (
        <div className="mt-4 border-t border-ash pt-4">
          <Button
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(sent, { onSuccess: () => toast({ message: `Saved: ${trait.name} in this troupe` }) })}
          >
            Save
          </Button>
        </div>
      )}
      <ErrorText error={save.error} />
    </Card>
  );
}
