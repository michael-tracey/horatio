import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { XpEntryOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

const KINDS: Record<string, string> = { self_entered: "self-entered", cap: "above a ceiling" };

/** The character's XP history. `selfEntering`: its player, while it has no home
 * troupe, may add XP to it themselves; the troupe it joins accepts or removes it. */
export function XpTab({ characterId, selfEntering = false }: { characterId: string; selfEntering?: boolean }) {
  const history = useQuery({
    queryKey: ["xp", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/xp", { params: { path: { character_id: characterId } } })),
  });
  if (history.isPending) return <Loading />;
  if (history.error) return <ErrorText error={history.error} />;
  let balance = 0;
  const rows = history.data.map((e) => ({ ...e, balance: (balance += e.amount) }));
  const reasons = new Map(history.data.map((e) => [e.id, e.reason]));
  return (
    <div className="flex flex-col gap-6">
      {selfEntering && <SelfEntered characterId={characterId} />}
      <Card title="Experience history">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-mist">
              <tr>
                <th className="py-2 pr-3 font-normal">Date</th>
                <th className="py-2 pr-3 font-normal">What</th>
                <th className="py-2 pr-3 text-right font-normal">XP</th>
                <th className="py-2 text-right font-normal">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {rows.reverse().map((e) => (
                <tr key={e.id}>
                  <td className="py-2 pr-3 align-top whitespace-nowrap text-mist">{e.entered_on}</td>
                  <td className="py-2 pr-3">
                    {e.reason}
                    {e.kind !== "purchase" && <span className="ml-2 text-xs text-mist">{KINDS[e.kind] ?? e.kind}</span>}
                    {e.corrects_id && <span className="block text-xs text-mist">Corrects “{reasons.get(e.corrects_id)}”</span>}
                    {e.corrected_to != null && <span className="block text-xs text-gold">Corrected: now gives {e.corrected_to} XP</span>}
                    {e.correctable && <Correct characterId={characterId} entry={e} />}
                  </td>
                  <td className={`py-2 pr-3 text-right align-top font-mono ${e.amount < 0 ? "text-blood-bright" : "text-gold"}`}>
                    {e.amount > 0 ? `+${e.amount}` : e.amount}
                  </td>
                  <td className="py-2 text-right align-top font-mono">{e.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/** XP the player adds themselves, such as for a character played elsewhere. */
function SelfEntered({ characterId }: { characterId: string }) {
  const [amount, setAmount] = useState(1);
  const [reason, setReason] = useState("");
  const add = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp/self-entered", { params: { path: { character_id: characterId } }, body: { amount, reason } }),
    );
    setReason("");
  });
  return (
    <Card title="Add XP yourself">
      <p className="mb-3 text-sm text-mist">
        For a character played somewhere else first. It is marked self-entered, and the troupe this character makes its home sees it apart and
        accepts or removes it.
      </p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined);
        }}
      >
        <Field label="XP">
          <Input type="number" min={1} required value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="w-24" />
        </Field>
        <div className="min-w-48 flex-1">
          <Field label="Why">
            <Input required maxLength={500} placeholder="Played at another troupe, 2024–25" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
        <Button type="submit" disabled={add.isPending || amount < 1 || !reason.trim()}>
          Add
        </Button>
        <ErrorText error={add.error} />
      </form>
    </Card>
  );
}

/** Put right a mistaken award: say what it should have given, and why. The award
 * stays in the history; a correction entry makes up the difference. */
function Correct({ characterId, entry }: { characterId: string; entry: XpEntryOut }) {
  const gives = entry.corrected_to ?? entry.amount;
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(gives);
  const [reason, setReason] = useState("");
  const correct = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp/{entry_id}/correction", {
        params: { path: { character_id: characterId, entry_id: entry.id } },
        body: { amount, reason },
      }),
    );
    setOpen(false);
    setReason("");
  });
  if (!open) {
    return (
      <button
        type="button"
        className="mt-1 block text-xs text-mist underline hover:text-parchment"
        onClick={() => {
          setAmount(gives);
          setOpen(true);
        }}
      >
        Correct this {entry.kind === "self_entered" ? "entry" : "award"}
      </button>
    );
  }
  const difference = amount - gives;
  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        correct.mutate(undefined);
      }}
    >
      <label className="flex items-center gap-2 text-xs text-mist">
        Should give
        <Input type="number" min={0} required value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="h-8 w-20 py-0" />
        XP
      </label>
      <Input aria-label="Why" placeholder="Why, such as a typo" required value={reason} onChange={(e) => setReason(e.target.value)} className="h-8 min-w-40 flex-1 py-0" />
      <Button type="submit" className="min-h-8" disabled={correct.isPending || difference === 0}>
        Correct
      </Button>
      <Button type="button" variant="ghost" className="min-h-8" onClick={() => setOpen(false)}>
        Cancel
      </Button>
      <p className="w-full text-xs text-mist">
        The award stays in the history; a correction of {difference > 0 ? `+${difference}` : difference} XP is added.
      </p>
      <ErrorText error={correct.error} />
    </form>
  );
}
