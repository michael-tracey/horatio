import { useEffect, useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CharacterOut, SheetOut, SheetTraitOut } from "../../../api/types";
import { Button, ErrorText } from "../../../components/ui";
import { useAction } from "../../../hooks";
import { FreeChoicesFields } from "../FreeChoices";
import { describePick, sayable, toSend, type FreePick } from "../freeChoices";

/** The merits the character holds that give free traits the player chooses. */
export function withFreeChoices(sheet: SheetOut, only?: string[]): SheetTraitOut[] {
  return sheet.traits.filter((t) => (t.rating ?? 0) > 0 && (t.free_choices ?? []).length > 0 && (!only || only.includes(t.name)));
}

const savedOf = (trait: SheetTraitOut): FreePick[] =>
  (trait.free_choices ?? []).flatMap((o) => o.picks.map((p) => ({ grant: o.grant, name: p.name, detail: p.detail, amount: p.amount })));

/**
 * The free traits a held merit gives (Ventrue Royalty: three backgrounds at 4, 3 and
 * 2), chosen where they land. The fields are the sheet's own (`FreeChoicesFields`);
 * the choices are saved with the button, and can change until a home troupe accepts
 * the character.
 */
export function FreeChoicesStep({ character, trait }: { character: CharacterOut; trait: SheetTraitOut }) {
  const offers = trait.free_choices ?? [];
  const saved = savedOf(trait);
  const savedKey = JSON.stringify(saved);
  const [draft, setDraft] = useState<FreePick[]>(saved);
  useEffect(() => setDraft(JSON.parse(savedKey) as FreePick[]), [savedKey]);
  const save = useAction((picks: FreePick[]) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits/choices", {
        params: { path: { character_id: character.id } },
        body: { category: trait.category, name: trait.name, detail: trait.detail, picks: toSend(picks) },
      }),
    ),
  );
  const locked = offers.find((o) => o.locked)?.locked ?? null;
  const same = JSON.stringify(toSend(draft)) === JSON.stringify(toSend(saved));
  const done = offers.every((o) => o.complete);
  return (
    <div className="ml-6 flex flex-col gap-2 rounded border border-ash p-2" role="group" aria-label={`Free traits from ${trait.name}`}>
      {locked ? (
        <>
          <p className="text-xs text-mist">{locked}</p>
          <p className="text-xs text-parchment">{saved.map(describePick).join(", ")}</p>
        </>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(draft);
          }}
        >
          <FreeChoicesFields offers={offers} picks={draft} onChange={setDraft} />
          <ErrorText error={save.error} />
          <div className="flex items-center gap-2">
            <Button type="submit" className="min-h-8 px-3 py-1 text-xs" disabled={save.isPending || same || !sayable(draft, offers)}>
              {done ? "Save changes" : "Save choices"}
            </Button>
            {!done && <span className="text-xs text-gold">Not chosen yet</span>}
          </div>
        </form>
      )}
    </div>
  );
}
