import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { everyone, nudge, totals, type Amounts } from "./xpAwards";

/**
 * A game's XP for the whole troupe at once: everyone at a set amount, raised or
 * lowered per character with the arrows (0 for someone who missed it), and one
 * note as the reason on every entry.
 */
export function XpAwardsTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const list = useQuery({ queryKey: ["xp-awards", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/xp-awards", path)) });
  const [setAmount, setSetAmount] = useState<number | null>(null);
  const [amounts, setAmounts] = useState<Amounts>({});
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [toRange, setToRange] = useState(true);
  const [done, setDone] = useState<string | null>(null);

  const characters = list.data?.characters ?? [];
  const ids = characters.map((c) => c.character_id);
  const set = setAmount ?? list.data?.session_xp ?? 8;
  // Everyone starts at the set amount, once the list arrives.
  useEffect(() => {
    if (list.data) setAmounts((now) => (Object.keys(now).length ? now : everyone(list.data.characters.map((c) => c.character_id), list.data.session_xp)));
  }, [list.data]);

  const award = useAction(async () => {
    const result = await unwrap(
      api.POST("/api/troupes/{troupe_id}/xp-awards", {
        ...path,
        body: {
          reason,
          awards: characters.map((c) => ({ character_id: c.character_id, amount: amounts[c.character_id] ?? 0 })),
          game_xp: toRange ? set : null,
        },
      }),
    );
    setDone(
      `Awarded ${result.total} XP to ${result.characters} character${result.characters === 1 ? "" : "s"} for “${reason.trim()}”.` +
        (toRange && set > 0 ? ` The floor and ceiling went up by ${set}.` : ""),
    );
    setConfirming(false);
    setReason("");
    setAmounts(everyone(ids, set));
  });

  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  if (!characters.length) {
    return (
      <Card title="Award XP">
        <Empty>No active player characters call this troupe home yet.</Empty>
      </Card>
    );
  }
  const sum = totals(amounts);
  const changeSet = (n: number) => {
    const next = Math.max(0, n);
    setSetAmount(next);
    setAmounts(everyone(ids, next));
    setConfirming(false);
  };

  return (
    <Card title="Award XP">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (confirming) award.mutate(undefined);
          else setConfirming(true);
        }}
      >
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Everyone gets" hint="Changing this resets every character to it.">
            <Stepper label="Everyone gets" value={set} onChange={changeSet} />
          </Field>
          <div className="min-w-60 flex-1">
            <Field label="Note everyone gets" hint="The reason on each character's XP history.">
              <Input
                required
                maxLength={500}
                placeholder="e.g. Game, 18 October"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  setConfirming(false);
                }}
              />
            </Field>
          </div>
        </div>

        <ul className="divide-y divide-ash border-y border-ash">
          {characters.map((c) => {
            const amount = amounts[c.character_id] ?? 0;
            return (
              <li key={c.character_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <span className={amount ? "" : "text-mist"}>
                  <Link to={`/characters/${c.character_id}`} className="hover:text-gold">
                    {c.character_name}
                  </Link>
                  <span className="ml-2 text-xs text-mist">{c.player_name}</span>
                  {amount !== set && <span className="ml-2 text-xs text-gold">{amount === 0 ? "nothing" : amount > set ? `+${amount - set}` : `${amount - set}`}</span>}
                </span>
                <Stepper
                  label={`XP for ${c.character_name}`}
                  value={amount}
                  onChange={(n) => {
                    setAmounts(nudge(amounts, c.character_id, n - amount));
                    setConfirming(false);
                  }}
                />
              </li>
            );
          })}
        </ul>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={toRange}
            onChange={(e) => {
              setToRange(e.target.checked);
              setConfirming(false);
            }}
          />
          Also add to floor and ceiling
          <span className="text-xs text-mist">(the {set} everyone gets, not each character's own amount)</span>
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm">
            {sum.total} XP to {sum.characters} of {characters.length} character{characters.length === 1 ? "" : "s"}
          </p>
          {confirming ? (
            <>
              <Button type="submit" disabled={award.isPending}>
                Yes, award {sum.total} XP
              </Button>
              <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                Back
              </Button>
            </>
          ) : (
            <Button type="submit" disabled={sum.characters === 0 || !reason.trim()}>
              Award…
            </Button>
          )}
        </div>
        {confirming && (
          <p role="status" className="text-sm text-gold">
            {sum.characters === 1 ? "One character gets" : `Each of ${sum.characters} characters gets`} an award entry for “{reason.trim()}”. A mistake can be
            corrected from the character's Experience tab.
            {toRange && set > 0 && ` The troupe's XP floor and ceiling go up by ${set}.`}
          </p>
        )}
        <ErrorText error={award.error} />
        {done && (
          <p role="status" className="text-sm text-gold">
            {done}
          </p>
        )}
      </form>
    </Card>
  );
}

/** A number with down and up arrows, never below 0. */
export function Stepper({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Button type="button" variant="secondary" className="min-h-9 w-9 px-0" aria-label={`Less ${label}`} disabled={value <= 0} onClick={() => onChange(value - 1)}>
        ▼
      </Button>
      <Input
        aria-label={label}
        type="number"
        min={0}
        max={1000}
        value={value}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        className="h-9 w-16 py-0 text-center"
      />
      <Button type="button" variant="secondary" className="min-h-9 w-9 px-0" aria-label={`More ${label}`} onClick={() => onChange(value + 1)}>
        ▲
      </Button>
    </span>
  );
}
