import type { FeedingIn, MyFeedingOut } from "../../api/types";
import { Button, Card, Field, Input, Notice, Select } from "../../components/ui";
import { herdShared, needText, tally } from "../../feeding";

/**
 * The Feeding section of the downtime form: feeding actions out of the general
 * actions, and the character's Herd shared out (its own feeding, gifts to other
 * characters, saved for game, other), never more dots than it has. The tally is
 * advisory; storytellers decide.
 */
export function FeedingCard({
  feeding,
  value,
  onChange,
  actionsLeft,
}: {
  feeding: MyFeedingOut;
  value: FeedingIn;
  onChange: (value: FeedingIn) => void;
  /** General actions not spent elsewhere on the form. */
  actionsLeft: number;
}) {
  const { needed, reasons } = needText(feeding.need);
  const counted = tally(feeding.need, value, feeding.received);
  const shared = herdShared(value);
  const gifts = value.gifts ?? [];
  const locked = feeding.locked;
  const number = (n: string) => Math.max(0, Number(n) || 0);
  const setGift = (i: number, change: Partial<(typeof gifts)[number]>) =>
    onChange({ ...value, gifts: gifts.map((g, j) => (j === i ? { ...g, ...change } : g)) });
  const unchosen = feeding.recipients.filter((r) => !gifts.some((g) => g.character_id === r.character_id));

  return (
    <Card title="Feeding">
      <p className="mb-3 text-sm">
        You need <strong className="text-gold">{needed}</strong> feeding this cycle: {reasons}.
      </p>
      {locked && <Notice>A storyteller has answered your feeding, so it can no longer change.</Notice>}
      <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
        <Field label="Actions spent feeding" hint={`Taken from your downtime actions (${actionsLeft} left).`}>
          <Input
            type="number"
            min={0}
            max={(value.actions ?? 0) + Math.max(0, actionsLeft)}
            disabled={locked}
            value={value.actions ?? 0}
            onChange={(e) => onChange({ ...value, actions: number(e.target.value) })}
          />
        </Field>
        <Field label="Where and how">
          <Input disabled={locked} value={value.where ?? ""} onChange={(e) => onChange({ ...value, where: e.target.value })} placeholder="Optional" />
        </Field>
      </div>

      {feeding.herd > 0 && (
        <fieldset className="mt-4 flex flex-col gap-3 border-t border-ash pt-3" disabled={locked}>
          <legend className="sr-only">Herd</legend>
          <p className="text-sm">
            Herd:{" "}
            <span className={shared > feeding.herd ? "text-blood-bright" : "text-mist"}>
              {shared} of your {feeding.herd} {feeding.herd === 1 ? "dot" : "dots"} shared out
            </span>
            {feeding.need.herd_factor !== 1 && (
              <span className="text-mist"> · {feeding.need.herd_factor === 0 ? "your Herd doesn't count towards your own feeding" : `each dot counts ${feeding.need.herd_factor}×`}</span>
            )}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Use for my feeding">
              <Input type="number" min={0} max={feeding.herd} value={value.herd_own ?? 0} onChange={(e) => onChange({ ...value, herd_own: number(e.target.value) })} />
            </Field>
            <Field label="Save for game" hint="Recorded for staff.">
              <Input type="number" min={0} max={feeding.herd} value={value.herd_saved ?? 0} onChange={(e) => onChange({ ...value, herd_saved: number(e.target.value) })} />
            </Field>
            <Field label="Other">
              <Input type="number" min={0} max={feeding.herd} value={value.herd_other ?? 0} onChange={(e) => onChange({ ...value, herd_other: number(e.target.value) })} />
            </Field>
          </div>
          {(value.herd_other ?? 0) > 0 && (
            <Field label="What the other dots are for">
              <Input value={value.herd_other_text ?? ""} onChange={(e) => onChange({ ...value, herd_other_text: e.target.value })} />
            </Field>
          )}
          {gifts.map((g, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_6rem_auto] sm:items-end">
              <Field label="Give to…">
                <Select value={g.character_id} onChange={(e) => setGift(i, { character_id: e.target.value })}>
                  {feeding.recipients
                    .filter((r) => r.character_id === g.character_id || unchosen.includes(r))
                    .map((r) => (
                      <option key={r.character_id} value={r.character_id}>
                        {r.name}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field label="Dots">
                <Input type="number" min={0} max={feeding.herd} value={g.amount ?? 0} onChange={(e) => setGift(i, { amount: number(e.target.value) })} />
              </Field>
              <Button variant="ghost" onClick={() => onChange({ ...value, gifts: gifts.filter((_, j) => j !== i) })}>
                Remove
              </Button>
            </div>
          ))}
          {unchosen.length > 0 && (
            <Button variant="secondary" className="self-start" onClick={() => onChange({ ...value, gifts: [...gifts, { character_id: unchosen[0]!.character_id, amount: 1 }] })}>
              Give Herd to another character
            </Button>
          )}
        </fieldset>
      )}

      {feeding.received.length > 0 && (
        <ul className="mt-4 text-sm">
          {feeding.received.map((r) => (
            <li key={r.character_id}>
              {r.character_name} gave you {r.amount} Herd.{!r.submitted && <span className="text-mist"> (Not submitted yet.)</span>}
            </li>
          ))}
        </ul>
      )}
      <p role="status" className={`mt-4 text-sm ${counted.enough ? "text-gold" : "text-mist"}`}>
        {counted.text}
      </p>
    </Card>
  );
}
