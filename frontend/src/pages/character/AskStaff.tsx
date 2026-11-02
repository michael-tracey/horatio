import { useState } from "react";
import type { TraitOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Button, Field, Input } from "../../components/ui";
import type { Exception } from "./cart";
import { detailNeed } from "./fields";
import { ChoiceSelect } from "./ChoiceSelect";

/**
 * Ask the home troupe's staff for a trait the rules refuse, as an exception:
 * why (one line, always), and whether at no XP cost. It goes in the cart as an
 * exception line; spending the cart makes it at once, waiting on staff.
 *
 * From the Add panel, `trait` is the catalogue trait asked for, and the form
 * also takes its detail and rating; from the cart, the line has them already.
 */
export function AskStaff({
  name,
  refusal,
  trait,
  fields = new Set<string>(),
  rated = false,
  maxRating,
  onAsk,
  onCancel,
}: {
  name: string;
  /** Why the rules refuse it, as they say. */
  refusal: string;
  trait?: TraitOut;
  /** Skills bought once per field: a choice of one asks for the field too. */
  fields?: Set<string>;
  rated?: boolean;
  maxRating?: number | null;
  onAsk: (exception: Exception, chosen: { detail: string; rating: number }) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [free, setFree] = useState(false);
  const shown = useClanName();
  const [detail, setDetail] = useState("");
  const need = detailNeed(trait);
  const [rating, setRating] = useState(1);
  const fixed = trait?.fixed_rating ?? null;
  return (
    <form
      aria-label={`Ask staff for ${shown(name)}`}
      className="flex flex-col gap-3 rounded-md border border-gold/40 bg-night/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onAsk({ reason: reason.trim(), free }, { detail, rating: fixed ?? rating });
      }}
    >
      <div className="text-sm">
        <p className="text-parchment">Ask staff for {shown(name)}</p>
        <p className="text-xs text-blood-bright">{shown(refusal)}</p>
        <p className="mt-1 text-xs text-mist">
          Staff can make an exception. It goes in the cart; once you spend it, {shown(name)} is on the sheet at once, waiting on the home troupe's approval.
        </p>
      </div>
      {trait?.choices ? (
        <Field label="Which?" hint={`${shown(trait.name)} gives one of these.`}>
          <ChoiceSelect required choices={trait.choices} fields={fields} value={detail} onChange={setDetail} />
        </Field>
      ) : (
        need && (
          <Field label={need.label} hint={need.hint}>
            <Input required placeholder={need.placeholder} value={detail} onChange={(e) => setDetail(e.target.value)} />
          </Field>
        )
      )}
      {trait && rated && fixed === null && (
        <Field label="Rating">
          <Input type="number" min={1} max={maxRating ?? undefined} value={rating} onChange={(e) => setRating(Number(e.target.value))} />
        </Field>
      )}
      <Field label="Why" hint={free ? "Say why it should be free: a plot reward, a ruling." : "One line for the storytellers."}>
        <Input required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={free} onChange={(e) => setFree(e.target.checked)} />
        Ask for it at no XP cost
      </label>
      <div className="flex gap-2">
        <Button type="submit" disabled={!reason.trim()}>
          Put it in the cart
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
