import { useState } from "react";
import type { TraitOut } from "../../api/types";
import { Button, Field, Input, Select } from "../../components/ui";
import type { Exception } from "./cart";
import { FIELD_PLACEHOLDER } from "./fields";

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
  rated = false,
  maxRating,
  onAsk,
  onCancel,
}: {
  name: string;
  /** Why the rules refuse it, as they say. */
  refusal: string;
  trait?: TraitOut;
  rated?: boolean;
  maxRating?: number | null;
  onAsk: (exception: Exception, chosen: { detail: string; rating: number }) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [free, setFree] = useState(false);
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const fixed = trait?.fixed_rating ?? null;
  return (
    <form
      aria-label={`Ask staff for ${name}`}
      className="flex flex-col gap-3 rounded-md border border-gold/40 bg-night/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onAsk({ reason: reason.trim(), free }, { detail, rating: fixed ?? rating });
      }}
    >
      <div className="text-sm">
        <p className="text-parchment">Ask staff for {name}</p>
        <p className="text-xs text-blood-bright">{refusal}</p>
        <p className="mt-1 text-xs text-mist">
          Staff can make an exception. It goes in the cart; once you spend it, {name} is on the sheet at once, waiting on the home troupe's approval.
        </p>
      </div>
      {trait?.choices ? (
        <Field label="Which?" hint={`${trait.name} gives one of these.`}>
          <Select required value={detail} onChange={(e) => setDetail(e.target.value)}>
            <option value="">Choose…</option>
            {trait.choices.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
        </Field>
      ) : (
        trait?.needs_field && (
          <Field label="Field" hint="Bought once per field.">
            <Input required placeholder={FIELD_PLACEHOLDER} value={detail} onChange={(e) => setDetail(e.target.value)} />
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
