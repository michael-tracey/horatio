import { useQuery } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { HarpyLedgerOut, PlayBoonIn, PlayBoonOut, PlayBoonsOut, PlayReportOut } from "../../api/types";
import { disgracedText } from "../../boonStatus";
import { BOON_PAGE, KINDS, kindName, type BoonKind } from "../../boons";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Field, Input, Loaded, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { playerSettles, reportedText, reportLine, settledText, standingFirst, type PlayerSettles } from "./boons";

/** Picked in "Who" for someone not on the list: an NPC, or a character of another domain. */
const SOMEONE_ELSE = "someone-else";

/**
 * The Play View's Boons tab (#686): the form to report a boon for the character, to
 * its troupe's boon ledger, and what the troupe lets its players see of the boons
 * the character owes and is owed. Where the troupe lets them, a boon's creditor's
 * player marks it settled here. Read from the phone with no signal like the rest of
 * the Play View; reporting and settling need one.
 */
export function BoonsTab({ characterId, name, online }: { characterId: string; name: string; online: boolean }) {
  const query = useQuery({
    queryKey: ["play-boons", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play-boons", { params: { path: { character_id: characterId } } })),
    refetchOnWindowFocus: false,
    retry: 2,
  });
  return (
    <section aria-label="Boons" className="flex flex-col gap-3">
      <Loaded query={query}>
        {(boons) => (
          <>
            {(boons.harpy ?? []).map((h) => (
              <HarpyCard key={h.troupe_id} characterId={characterId} name={name} ledger={h} online={online} />
            ))}
            <Report characterId={characterId} name={name} boons={boons} online={online} />
            {boons.reports && boons.reports.length > 0 && <Reports reports={boons.reports} name={name} troupe={boons.troupe_name} />}
            {boons.owes && <Side title={`${name} owes`} empty={`${name} owes no boons in the ledger.`} boons={boons.owes} owes name={name} characterId={characterId} online={online} />}
            {boons.owed && (
              <Side title={`Owed to ${name}`} empty={`No boons in the ledger are owed to ${name}.`} boons={boons.owed} owes={false} name={name} characterId={characterId} online={online} />
            )}
          </>
        )}
      </Loaded>
    </section>
  );
}

/** For the troupe's Harpy (#688): a way to the ledger they keep, and how many boons wait for review. */
function HarpyCard({ characterId, name, ledger, online }: { characterId: string; name: string; ledger: HarpyLedgerOut; online: boolean }) {
  const full = ledger.access === "full";
  return (
    <Card title={`${name}, Harpy of ${ledger.troupe_name}`}>
      <p className="text-sm text-mist">
        {full ? "You keep the troupe's boon ledger: register, edit and settle boons, and review what players report." : "You review the boons players report."}
        {ledger.to_review > 0 ? ` ${ledger.to_review} to review.` : " Nothing waits for review."}
      </p>
      {online ? (
        <Link to={`/play/characters/${characterId}/ledger`} className="mt-2 inline-flex min-h-10 items-center text-sm text-gold underline hover:text-parchment">
          {full ? "Open the boon ledger" : "Review boons"}
        </Link>
      ) : (
        <p className="mt-2 text-xs text-mist">The ledger needs a signal.</p>
      )}
    </Card>
  );
}

type Draft = {
  direction: PlayBoonIn["direction"];
  who: string;
  other: string;
  kind: BoonKind;
  madeOn: string;
  reason: string;
  conditions: string;
  notify: boolean;
  count: number;
};

function fresh(today: string): Draft {
  return { direction: "owes", who: "", other: "", kind: "minor", madeOn: today, reason: "", conditions: "", notify: false, count: 1 };
}

/** Report a boon: open at once where it's all the tab has, else behind a button. */
function Report({ characterId, name, boons, online }: { characterId: string; name: string; boons: PlayBoonsOut; online: boolean }) {
  const dates = useDates();
  const toast = useToast();
  const today = dates.toInput(new Date()).slice(0, 10);
  const formOnly = boons.see === "intake";
  const [open, setOpen] = useState(formOnly);
  const [draft, setDraft] = useState<Draft>(() => fresh(today));
  const set = (change: Partial<Draft>) => setDraft((d) => ({ ...d, ...change }));
  const directionName = useId();
  const report = useAction(
    async (body: PlayBoonIn) => {
      const after = await unwrap(api.POST("/api/characters/{character_id}/play-boons", { params: { path: { character_id: characterId } }, body }));
      // Held for review (#687): it shows among the reports waiting.
      const waiting = (b: PlayBoonsOut) => (b.reports ?? []).filter((r) => r.state === "pending").length;
      return { body, waits: waiting(after) > waiting(boons) };
    },
    [["play-boons", characterId]],
  );

  if (!boons.can_report) return <p className="text-sm text-mist">{name} isn&apos;t in play in {boons.troupe_name}, so reports no boons.</p>;
  if (!open)
    return (
      <Button variant="secondary" className="self-start" onClick={() => setOpen(true)}>
        Report a boon
      </Button>
    );

  const someoneElse = draft.who === SOMEONE_ELSE;
  const other = boons.characters.find((c) => c.id === draft.who);
  const otherName = someoneElse ? draft.other.trim() : (other?.name ?? "");
  const ready = !!otherName && !!draft.madeOn && draft.count >= 1;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!ready || !online) return;
    report.mutate(
      {
        other: someoneElse ? { name: otherName } : { character_id: draft.who, name: "" },
        direction: draft.direction,
        kind: draft.kind,
        made_on: draft.madeOn,
        reason: draft.reason,
        conditions: draft.conditions,
        notify_on_trade: draft.notify,
        count: draft.count,
      },
      {
        onSuccess: ({ body, waits }) => {
          toast({ message: reportedText(name, otherName, body.direction, body.kind, body.count ?? 1, boons.troupe_name, waits) });
          setDraft(fresh(today));
          if (!formOnly) setOpen(false);
        },
      },
    );
  };
  const meaning = KINDS.find((k) => k.value === draft.kind)?.meaning;

  return (
    <Card title="Report a boon" dense>
      <form className="flex flex-col gap-3" onSubmit={submit} aria-label="Report a boon">
        <p className="text-xs text-mist">
          It goes in {boons.troupe_name}&apos;s boon ledger, which its staff keep ({BOON_PAGE}). A boon made off the record isn&apos;t enforced.
        </p>
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="mb-1 text-mist">Which way</legend>
          {(["owes", "owed"] as const).map((d) => (
            <label key={d} className="flex min-h-10 items-center gap-2">
              <input type="radio" name={directionName} checked={draft.direction === d} onChange={() => set({ direction: d })} />
              {d === "owes" ? `${name} owes them` : `They owe ${name}`}
            </label>
          ))}
        </fieldset>
        <Field label="Who">
          <Select value={draft.who} onChange={(e) => set({ who: e.target.value })} required>
            <option value="">Choose…</option>
            {boons.characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
            <option value={SOMEONE_ELSE}>Someone else…</option>
          </Select>
        </Field>
        {someoneElse && (
          <Field label="Their name" hint="An NPC, or someone from another domain. Staff link the name to the ledger.">
            <Input value={draft.other} maxLength={200} onChange={(e) => set({ other: e.target.value })} required />
          </Field>
        )}
        <Field label="Kind" hint={meaning}>
          <Select value={draft.kind} onChange={(e) => set({ kind: e.target.value as BoonKind })}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="The night it was made" hint={dates.inputText(draft.madeOn)}>
          <DateInput value={draft.madeOn} onChange={(e) => set({ madeOn: e.target.value })} required />
        </Field>
        <Field label="Reason">
          <Input value={draft.reason} maxLength={2000} onChange={(e) => set({ reason: e.target.value })} placeholder="Information, an introduction…" />
        </Field>
        <Field label="Conditions" hint="Anything agreed with it, such as “Cannot be traded” or “No clan secrets”.">
          <Input value={draft.conditions} maxLength={2000} onChange={(e) => set({ conditions: e.target.value })} />
        </Field>
        <label className="flex min-h-10 items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.notify} onChange={(e) => set({ notify: e.target.checked })} />
          Tell the debtor&apos;s player if it&apos;s traded
        </label>
        <Field label="How many" hint="Several alike, such as three minor boons for the same thing.">
          <Input type="number" inputMode="numeric" min={1} max={20} className="w-24" value={draft.count} onChange={(e) => set({ count: Math.max(1, Math.min(20, Number(e.target.value) || 1)) })} />
        </Field>
        {!online && <p className="text-sm text-blood">Reporting a boon needs a connection. It can be sent once you have signal again.</p>}
        <ErrorText error={report.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!ready || !online || report.isPending}>
            {draft.count > 1 ? `Report ${draft.count} boons` : "Report the boon"}
          </Button>
          {!formOnly && (
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}

/** One side of the character's boons: those standing, then those settled, folded away. */
function Side({
  title,
  empty,
  boons,
  owes,
  name,
  characterId,
  online,
}: {
  title: string;
  empty: string;
  boons: PlayBoonOut[];
  owes: boolean;
  name: string;
  characterId: string;
  online: boolean;
}) {
  const { standing, settled } = standingFirst(boons);
  return (
    <Card title={title} dense>
      <div role="region" aria-label={title}>
        {standing.length === 0 ? (
          <p className="text-sm text-mist">{empty}</p>
        ) : (
          <ul className="divide-y divide-ash/60">
            {standing.map((b) => (
              <BoonRow key={b.id} boon={b} owes={owes} creditor={owes ? b.other : name} characterId={characterId} online={online} />
            ))}
          </ul>
        )}
        {settled.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-sm text-mist">Settled ({settled.length})</summary>
            <ul className="divide-y divide-ash/60">
              {settled.map((b) => (
                <BoonRow key={b.id} boon={b} owes={owes} creditor={owes ? b.other : name} characterId={characterId} online={online} />
              ))}
            </ul>
          </details>
        )}
      </div>
    </Card>
  );
}

function BoonRow({
  boon,
  owes,
  creditor,
  characterId,
  online,
}: {
  boon: PlayBoonOut;
  owes: boolean;
  /** Whom it is owed to, by name. */
  creditor: string;
  characterId: string;
  online: boolean;
}) {
  const dates = useDates();
  const [settling, setSettling] = useState(false);
  return (
    <li className="py-2 text-sm" aria-label={`${kindName(boon.kind)} boon ${owes ? "to" : "from"} ${boon.other}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p>
          <strong className="font-semibold text-parchment">{kindName(boon.kind)}</strong>
          <span className="text-mist"> {owes ? "to" : "from"} </span>
          {boon.other}
          <span className="text-mist"> · {dates.day(boon.made_on)}</span>
        </p>
        {boon.can_settle && !settling && (
          <Button variant="secondary" className="min-h-9 px-3" disabled={!online} onClick={() => setSettling(true)}>
            Settle
          </Button>
        )}
      </div>
      {boon.reason && <p className="text-mist">{boon.reason}</p>}
      {boon.conditions && <p className="text-xs text-mist">Conditions: {boon.conditions}</p>}
      {boon.notify_on_trade && <p className="text-xs text-mist">Its debtor&apos;s player is told if it&apos;s traded.</p>}
      {boon.creditor_disgraced && <p className="text-xs text-blood-bright">{disgracedText(creditor)}</p>}
      {boon.state === "settled" && <p className="text-xs text-mist">{settledText(boon, dates.day)}</p>}
      {settling && <Settle boon={boon} characterId={characterId} online={online} done={() => setSettling(false)} />}
    </li>
  );
}

/** The creditor's player marks a boon settled: called in, or forgiven. */
function Settle({ boon, characterId, online, done }: { boon: PlayBoonOut; characterId: string; online: boolean; done: () => void }) {
  const [how, setHow] = useState<PlayerSettles>("called_in");
  const [note, setNote] = useState("");
  const name = useId();
  const settle = useAction(
    () =>
      unwrap(
        api.POST("/api/characters/{character_id}/play-boons/{boon_id}/settle", {
          params: { path: { character_id: characterId, boon_id: boon.id } },
          body: { how, note },
        }),
      ),
    [["play-boons", characterId]],
  );
  return (
    <form
      className="mt-2 flex flex-col gap-2 rounded-md border border-ash p-2"
      aria-label="Settle the boon"
      onSubmit={(e) => {
        e.preventDefault();
        settle.mutate(undefined, { onSuccess: done });
      }}
    >
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-mist">How it was settled</legend>
        {playerSettles.map((s) => (
          <label key={s.value} className="flex min-h-10 items-center gap-2">
            <input type="radio" name={name} checked={how === s.value} onChange={() => setHow(s.value)} />
            <span>
              {s.label}
              <span className="block text-xs text-mist">{s.meaning}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <Field label="Note (optional)">
        <Input value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} placeholder="Called in for…" />
      </Field>
      <ErrorText error={settle.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!online || settle.isPending}>
          Mark it settled
        </Button>
        <Button type="button" variant="secondary" onClick={done}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The player's reports that wait for review, or weren't accepted lately, with why (#687). */
function Reports({ reports, name, troupe }: { reports: PlayReportOut[]; name: string; troupe: string }) {
  const dates = useDates();
  return (
    <Card title="Your reports" dense>
      <ul aria-label="Your reports" className="divide-y divide-ash/60">
        {reports.map((r) => (
          <li key={r.id} className="py-2 text-sm">
            <p>
              {reportLine(r, name)}
              <span className="text-mist"> · {dates.day(r.made_on)}</span>
            </p>
            {r.reason && <p className="text-mist">{r.reason}</p>}
            {r.state === "pending" ? (
              <p className="text-xs text-mist">Waiting for {troupe}&apos;s staff to review it.</p>
            ) : (
              <p className="text-xs text-blood-bright">Not accepted{r.rejected_at ? `, ${dates.day(r.rejected_at)}` : ""}: {r.rejected_because}</p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
