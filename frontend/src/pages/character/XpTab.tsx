import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { XpEntryOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

const KINDS: Record<string, string> = { self_entered: "self-entered", cap: "above a ceiling", reprice: "repriced", debt: "XP debt" };
// Lines whose reason says all there is: a purchase, and creation XP lost when accepted.
const UNLABELLED = new Set(["purchase", "lost"]);

/** The character's XP history. `selfEntering`: its player, while it has no home
 * troupe, may add XP to it themselves; the troupe it joins accepts or removes it. */
export function XpTab({ characterId, selfEntering = false }: { characterId: string; selfEntering?: boolean }) {
  const history = useQuery({
    queryKey: ["xp", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/xp", { params: { path: { character_id: characterId } } })),
  });
  const dates = useDates();
  if (history.isPending) return <Loading />;
  if (history.error) return <ErrorText error={history.error} />;
  let balance = 0;
  const rows = history.data.map((e) => ({ ...e, balance: (balance += e.amount) }));
  const reasons = new Map(history.data.map((e) => [e.id, e.reason]));
  return (
    <div className="flex flex-col gap-6">
      {selfEntering && <SelfEntered characterId={characterId} />}
      <DebtCard characterId={characterId} />
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
                  <td className="py-2 pr-3 align-top whitespace-nowrap text-mist">
                    <time dateTime={e.entered_on}>{dates.day(e.entered_on)}</time>
                  </td>
                  <td className="py-2 pr-3">
                    {e.reason}
                    {!UNLABELLED.has(e.kind) && <span className="ml-2 text-xs text-mist">{KINDS[e.kind] ?? e.kind}</span>}
                    {e.kind === "correction" && e.corrects_id && <span className="block text-xs text-mist">Corrects “{reasons.get(e.corrects_id)}”</span>}
                    {e.corrected_to != null && <span className="block text-xs text-gold">Corrected: now gives {e.corrected_to} XP</span>}
                    {e.to_debt > 0 && (
                      <span className="block text-xs text-gold">
                        {e.to_debt} XP to the debt{e.debt > 0 ? `; ${e.debt} still owed` : "; it is paid off"}
                      </span>
                    )}
                    {e.correctable && <Correct characterId={characterId} entry={e} />}
                  </td>
                  <td className={`py-2 pr-3 text-right align-top font-mono ${e.amount < 0 ? "text-blood-bright" : "text-gold"}`}>
                    {e.amount > 0 ? `+${e.amount}` : e.amount}
                  </td>
                  <td className={`py-2 text-right align-top font-mono ${e.balance < 0 ? "text-blood-bright" : ""}`} title={e.balance < 0 ? `${-e.balance} XP owed` : undefined}>
                    {e.balance}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/**
 * XP debt, from a ghoul's Embrace or put on by staff: what it comes to, and for the
 * home troupe's storytellers and assistants, a way to add to it or forgive some.
 * The XP the character earns pays it off first.
 */
function DebtCard({ characterId }: { characterId: string }) {
  const path = { path: { character_id: characterId } };
  const debt = useQuery({
    queryKey: ["xp-debt", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/xp/debt", { params: path })),
  });
  const [change, setChange] = useState<"add" | "forgive">("add");
  const [amount, setAmount] = useState(1);
  const [reason, setReason] = useState("");
  const save = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/xp/debt", { params: path, body: { change, amount, reason } }));
    setReason("");
  });
  if (!debt.data || (!debt.data.debt && !debt.data.can_change)) return null;
  return (
    <Card title="XP debt">
      <p className="mb-3 text-sm">
        {debt.data.debt > 0 ? `${debt.data.debt} XP owed. All the XP the character earns goes to it until it is paid off, and nothing new can be bought till then.` : "None owed."}
      </p>
      {debt.data.can_change && (
        <form
          aria-label="Change the XP debt"
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <Field label="Debt">
            <Select value={change} onChange={(e) => setChange(e.target.value as "add" | "forgive")}>
              <option value="add">Add</option>
              <option value="forgive">Forgive</option>
            </Select>
          </Field>
          <Field label="XP" hint={change === "add" ? "Unspent XP pays it first." : undefined}>
            <Input type="number" min={1} required value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="w-24" />
          </Field>
          <div className="min-w-48 flex-1">
            <Field label="Why">
              <Input required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          </div>
          <Button type="submit" disabled={save.isPending || amount < 1 || !reason.trim()}>
            {change === "add" ? "Add debt" : "Forgive debt"}
          </Button>
          <ErrorText error={save.error} />
        </form>
      )}
    </Card>
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
