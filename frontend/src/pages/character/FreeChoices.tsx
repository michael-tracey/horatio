import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, FreeChoicesOut, SheetTraitOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import {
  describePick,
  fill,
  heading,
  optionOf,
  place,
  placed,
  pointsUsed,
  picksOf,
  rule,
  sayable,
  setDetail,
  slot,
  toggle,
  toSend,
  type FreePick,
} from "./freeChoices";

/**
 * The fields for choosing the free traits a merit gives (Ventrue Royalty and five
 * more), one block for each thing it gives. It holds nothing itself: the picks are
 * the caller's, so the Add panel can keep them in the cart, the sheet can save
 * them, and the creation wizard can use it as it is.
 */
export function FreeChoicesFields({
  offers,
  picks,
  onChange,
}: {
  offers: FreeChoicesOut[];
  picks: FreePick[];
  onChange: (picks: FreePick[]) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {offers.map((offer) => (
        <fieldset key={offer.grant} className="flex flex-col gap-2 rounded border border-ash p-2">
          <legend className="px-1 text-sm text-parchment">{heading(offer)}</legend>
          <p className="text-xs text-mist">{rule(offer)}</p>
          {offer.places ? (
            <Places offer={offer} picks={picks} onChange={onChange} />
          ) : offer.points != null ? (
            <Budget offer={offer} picks={picks} onChange={onChange} />
          ) : (
            <Slots offer={offer} picks={picks} onChange={onChange} />
          )}
        </fieldset>
      ))}
    </div>
  );
}

type Part = { offer: FreeChoicesOut; picks: FreePick[]; onChange: (picks: FreePick[]) => void };

/** Dots to place, one amount for each different trait. */
function Places({ offer, picks, onChange }: Part) {
  const taken = new Set(picksOf(picks, offer).map((p) => p.name));
  return (
    <div className="flex flex-wrap gap-3">
      {offer.places!.map((amount) => {
        const here = placed(picks, offer, amount)?.name ?? "";
        return (
          <Field key={amount} label={`${amount} dots in`}>
            <Select value={here} onChange={(e) => onChange(place(picks, offer, amount, e.target.value))}>
              <option value="">Choose…</option>
              {offer.options.map((o) => (
                <option key={o.name} value={o.name} disabled={taken.has(o.name) && o.name !== here}>
                  {o.name}
                </option>
              ))}
            </Select>
          </Field>
        );
      })}
    </div>
  );
}

/** A few traits to choose, each in a slot of its own (with its words, for a "Custom" one). */
function Slots({ offer, picks, onChange }: Part) {
  const count = offer.count ?? 1;
  const chosen = new Set(picksOf(picks, offer).map((p) => `${p.name}/${p.detail}`));
  return (
    <div className="flex flex-wrap gap-3">
      {Array.from({ length: count }, (_, i) => {
        const here = slot(picks, offer, i);
        const need = here && optionOf(offer, here.name)?.needs_detail;
        return (
          <div key={i} className="flex flex-col gap-1">
            <Field label={count === 1 ? `Your free ${offer.category_name.toLowerCase()}` : `${offer.category_name}, choice ${i + 1}`}>
              <Select value={here?.name ?? ""} onChange={(e) => onChange(fill(picks, offer, i, e.target.value))}>
                <option value="">Choose…</option>
                {offer.options.map((o) => (
                  <option key={o.name} value={o.name} disabled={!o.needs_detail && chosen.has(`${o.name}/`) && o.name !== here?.name}>
                    {o.name}
                    {o.rating ? ` (${o.rating})` : ""}
                  </option>
                ))}
              </Select>
            </Field>
            {here && need && (
              <Input
                aria-label={`${here.name}, in your words (choice ${i + 1})`}
                placeholder={here.name === "Custom" ? "In your own words" : "Which?"}
                maxLength={200}
                value={here.detail}
                onChange={(e) => onChange(fill(picks, offer, i, here.name, e.target.value))}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Merits to tick, up to a number of points. */
function Budget({ offer, picks, onChange }: Part) {
  const used = pointsUsed(picks, offer);
  const mine = picksOf(picks, offer);
  return (
    <>
      <p className="text-xs text-gold">
        {used} of {offer.points} points
      </p>
      <ul className="flex max-h-60 flex-col overflow-y-auto">
        {offer.options.map((o) => {
          const on = mine.find((p) => p.name === o.name);
          const fits = used + (o.rating ?? 0) <= (offer.points ?? 0);
          return (
            <li key={o.name} className={`flex flex-wrap items-center gap-2 px-1 py-0.5 text-sm ${!on && !fits ? "opacity-50" : ""}`}>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={!!on} disabled={!on && !fits} onChange={(e) => onChange(toggle(picks, offer, o.name, e.target.checked))} />
                {o.name}
                {o.rating ? <span className="text-gold"> ({o.rating})</span> : null}
              </label>
              {on && o.needs_detail && (
                <Input
                  aria-label={`${o.name}, which?`}
                  placeholder="Which?"
                  maxLength={200}
                  className="min-h-8 w-44 py-1 text-xs"
                  value={on.detail}
                  onChange={(e) => onChange(setDetail(picks, offer, o.name, on.detail, e.target.value))}
                />
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/**
 * Under a merit on the sheet: the free traits its player chose, and until a home
 * troupe accepts the character, a way to choose or change them.
 */
export function FreeChoicesRow({ character, trait, editable }: { character: CharacterOut; trait: SheetTraitOut; editable: boolean }) {
  const offers = trait.free_choices;
  const saved = offers.flatMap((o) => o.picks.map((p) => ({ grant: o.grant, name: p.name, detail: p.detail, amount: p.amount })));
  const [draft, setDraft] = useState<FreePick[] | null>(null);
  const save = useAction((picks: FreePick[]) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits/choices", {
        params: { path: { character_id: character.id } },
        body: { category: trait.category, name: trait.name, detail: trait.detail, picks: toSend(picks) },
      }),
    ),
  );
  if (offers.length === 0) return null;
  const locked = offers.find((o) => o.locked)?.locked ?? null;
  const open = editable && !locked;
  const done = offers.every((o) => o.complete);

  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs" data-free-choices={trait.name}>
      {offers.map((o) => (
        <p key={o.grant} className="flex flex-wrap items-center gap-1.5">
          <span className={o.picks.length === 0 ? "text-gold" : "text-mist"}>{o.category_name.replace(/^./, (c) => c.toUpperCase())} given free:</span>
          {o.picks.length === 0 && <span className="text-gold">not chosen yet</span>}
          {o.picks.map((p) => (
            <span key={`${p.name}/${p.detail}`} className="rounded border border-ash px-1.5 text-parchment">
              {describePick(p)}
            </span>
          ))}
        </p>
      ))}
      {draft === null && open && (
        <Button
          variant="ghost"
          className="min-h-7 px-1 py-0 text-xs text-gold"
          aria-label={`${done ? "Change" : "Choose"} the free traits for ${trait.name}`}
          onClick={() => setDraft(saved)}
        >
          {done ? "Change" : "Choose"}
        </Button>
      )}
      {locked && saved.length > 0 && <p className="text-mist">{locked}</p>}
      {draft !== null && (
        <form
          className="mt-1.5 flex flex-col gap-2 rounded border border-ash bg-night/50 p-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(draft, { onSuccess: () => setDraft(null) });
          }}
        >
          <FreeChoicesFields offers={offers} picks={draft} onChange={setDraft} />
          <ErrorText error={save.error} />
          <div className="flex gap-2">
            <Button type="submit" className="min-h-8 px-3 py-1 text-xs" disabled={save.isPending || !sayable(draft, offers)}>
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="min-h-8 px-3 py-1 text-xs"
              onClick={() => {
                save.reset();
                setDraft(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
