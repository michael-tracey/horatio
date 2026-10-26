import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { OfferOut, SheetOut, SheetTraitOut } from "../../api/types";
import { HouseMark } from "../../components/HouseMark";
import { Button, Card, ErrorText, Field, Input } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * For the troupe's running staff: its house merits and flaws, to apply to the
 * character (free or charged, with a reason for the logs) and to take off again.
 * Shown only where the character's home troupe, or the troupe it is built for,
 * has some; never for a character only visiting.
 */
export function HouseTraitsCard({ characterId, sheet }: { characterId: string; sheet: SheetOut }) {
  const offers = useQuery({
    queryKey: ["house-offers", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/house-traits", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
  const [applying, setApplying] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  if (!offers.data) return null;
  const held = sheet.traits.filter((t) => t.house);
  const open = offers.data.filter((o) => !o.held);
  if (open.length === 0 && held.length === 0) return null;

  return (
    <Card dense title="House merits and flaws">
      {open.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {open.map((o) => (
            <li key={o.id} className="flex flex-col gap-1">
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {o.name} <span className="text-gold">({o.points})</span>
                  <HouseMark label={o.label} short />
                  {o.availability === "staff" && <span className="ml-1 text-xs text-mist">staff only</span>}
                </span>
                {applying !== o.id && (
                  <Button variant="ghost" className="min-h-7 px-2" aria-label={`Apply ${o.name}`} onClick={() => setApplying(o.id)}>
                    Apply
                  </Button>
                )}
              </span>
              {applying === o.id && <ApplyForm characterId={characterId} offer={o} onDone={() => setApplying(null)} />}
            </li>
          ))}
        </ul>
      )}
      {held.length > 0 && (
        <ul className={`flex flex-col gap-2 text-sm ${open.length > 0 ? "mt-3 border-t border-ash pt-2" : ""}`}>
          {held.map((t) => (
            <li key={t.id} className="flex flex-col gap-1">
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {t.name}
                  <HouseMark label={t.house!.label} short />
                  <span className="ml-1 text-xs text-mist">
                    {t.house!.applied ? `applied${t.house!.applied.free ? ", free" : ""}` : "taken by the player"}
                  </span>
                </span>
                {removing !== t.id && (
                  <Button variant="ghost" className="min-h-7 px-2" aria-label={`Remove ${t.name}`} onClick={() => setRemoving(t.id)}>
                    Remove
                  </Button>
                )}
              </span>
              {removing === t.id && <RemoveForm characterId={characterId} trait={t} onDone={() => setRemoving(null)} />}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ApplyForm({ characterId, offer, onDone }: { characterId: string; offer: OfferOut; onDone: () => void }) {
  const [free, setFree] = useState(true);
  const [counts, setCounts] = useState(true);
  const [reason, setReason] = useState("");
  const flaw = offer.category === "flaws";
  const apply = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/house-traits", {
        params: { path: { character_id: characterId } },
        body: { house_trait_id: offer.id, free, counts_toward_limit: counts, reason: reason.trim() },
      }),
    );
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-2 rounded-md border border-ash p-2"
      onSubmit={(e) => {
        e.preventDefault();
        apply.mutate(undefined);
      }}
    >
      {offer.description && <p className="text-xs text-mist">{offer.description}</p>}
      <fieldset className="flex flex-col gap-1 text-sm">
        <legend className="sr-only">Cost</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name={`cost-${offer.id}`} checked={free} onChange={() => setFree(true)} />
          Free{flaw ? ", giving no XP" : ", costing no XP"}
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name={`cost-${offer.id}`} checked={!free} onChange={() => setFree(false)} />
          {flaw ? `Charged: gives ${offer.points} XP back` : `Charged: ${offer.points} XP`}
        </label>
        {free && !flaw && (
          <label className="ml-6 flex items-center gap-2">
            <input type="checkbox" checked={counts} onChange={(e) => setCounts(e.target.checked)} />
            Counts toward the 7-point merit limit
          </label>
        )}
      </fieldset>
      <Field label="Reason" hint="It goes in the character's log and the troupe's.">
        <Input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" disabled={!reason.trim() || apply.isPending}>
          Apply {offer.name}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <ErrorText error={apply.error} />
    </form>
  );
}

function RemoveForm({ characterId, trait, onDone }: { characterId: string; trait: SheetTraitOut; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const remove = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/house-traits/{house_trait_id}/remove", {
        params: { path: { character_id: characterId, house_trait_id: trait.house!.house_trait_id } },
        body: { reason: reason.trim() },
      }),
    );
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-2 rounded-md border border-ash p-2"
      onSubmit={(e) => {
        e.preventDefault();
        remove.mutate(undefined);
      }}
    >
      <Field label="Reason" hint="It goes in the character's log and the troupe's.">
        <Input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" disabled={!reason.trim() || remove.isPending}>
          Remove {trait.name}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <ErrorText error={remove.error} />
    </form>
  );
}
