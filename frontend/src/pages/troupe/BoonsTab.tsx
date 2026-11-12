import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BoonOut, CharacterChoice } from "../../api/types";
import { partyIn } from "../../bonds";
import {
  actionsFor,
  BOON_PAGE,
  changeText,
  emptyRow,
  eventName,
  KINDS,
  kindName,
  owes,
  partyName,
  rowStarted,
  rowsTotal,
  SETTLED,
  stateText,
  VIEWS,
  type BoonKind,
  type BoonView,
  type EntryRow,
  type SettledHow,
} from "../../boons";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { WhoPicker } from "./WhoPicker";

function today(dates: ReturnType<typeof useDates>) {
  return dates.toInput(new Date()).slice(0, 10);
}

/** A picked side ("c:<id>" or "name"), from a party the API sent. */
function picked(party: BoonOut["debtor"]): { who: string; name: string } {
  return party.character_id ? { who: `c:${party.character_id}`, name: "" } : { who: "name", name: party.name };
}

/**
 * The troupe's boon ledger, for its running staff (#685): every boon, by view (open,
 * departed, settled, void, all), narrowed to a character or a name, a kind, or a span
 * of nights. Staff register boons, a whole game's at once, and open one to edit,
 * trade, pass on, settle, void or reopen it, each with its own log. Only shown while
 * the troupe keeps a ledger.
 */
export function BoonsTab({ troupeId }: { troupeId: string }) {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<BoonView>("open");
  const [who, setWho] = useState<{ who: string; name: string }>(() => {
    const character = params.get("character");
    return character ? { who: `c:${character}`, name: "" } : { who: "", name: "" };
  });
  const [kind, setKind] = useState<BoonKind | "">("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  // Bumped to empty the character box when the filters are cleared.
  const [cleared, setCleared] = useState(0);
  const query = {
    view,
    ...(who.who.startsWith("c:") ? { character_id: who.who.slice(2) } : {}),
    ...(who.who === "name" && who.name.trim() ? { name: who.name.trim() } : {}),
    ...(kind ? { kind } : {}),
    ...(from ? { made_from: from } : {}),
    ...(to ? { made_to: to } : {}),
  };
  const ledger = useQuery({
    queryKey: ["troupe-boons", troupeId, query],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/boons", {
          params: { path: { troupe_id: troupeId }, query },
        }),
      ),
    placeholderData: (previous) => previous,
  });
  if (ledger.isPending) return <Loading />;
  if (ledger.error) return <ErrorText error={ledger.error} />;
  const { boons, counts, characters } = ledger.data;
  const narrowed = Boolean(who.who || kind || from || to);
  const clear = () => {
    setWho({ who: "", name: "" });
    setKind("");
    setFrom("");
    setTo("");
    setCleared(cleared + 1);
    if (params.has("character")) setParams({}, { replace: true });
  };

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Boon ledger"
        actions={
          !adding && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Register boons
            </Button>
          )
        }
      >
        <p className="text-sm text-mist">
          The debts characters owe each other, registered with the Harpy ({BOON_PAGE}). Each boon keeps its own log; an edit&apos;s changes show only to
          storytellers and assistant storytellers. A boon made off the record isn&apos;t tracked here.
        </p>
        {adding && <QuickEntry troupeId={troupeId} characters={characters} onDone={() => setAdding(false)} />}
      </Card>

      <div className="flex flex-col gap-3">
        <div role="tablist" aria-label="Ledger views" className="flex flex-wrap gap-1">
          {VIEWS.filter((v) => v.value !== "pending" || (counts.pending ?? 0) > 0).map((v) => (
            <Button
              key={v.value}
              role="tab"
              aria-selected={view === v.value}
              variant={view === v.value ? "secondary" : "ghost"}
              onClick={() => {
                setView(v.value);
                setOpen(null);
              }}
            >
              {v.label} <span className="text-mist">({counts[v.value] ?? 0})</span>
            </Button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Character or name">
            <WhoPicker key={cleared} characters={characters} who={who.who} name={who.name} onChange={(w, name) => setWho({ who: w, name })} />
          </Field>
          <Field label="Kind">
            <Select value={kind} onChange={(e) => setKind(e.target.value as BoonKind | "")}>
              <option value="">Any kind</option>
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Made from">
            <DateInput value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="Made to">
            <DateInput value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
        {narrowed && (
          <div>
            <Button variant="ghost" onClick={clear}>
              Show every boon
            </Button>
          </div>
        )}
      </div>

      {boons.length === 0 ? (
        <Empty>{narrowed ? "No boons match." : view === "open" ? "No open boons yet." : "None here."}</Empty>
      ) : (
        <ul aria-label="Boons" aria-busy={ledger.isPlaceholderData} className={`flex flex-col gap-2 ${ledger.isPlaceholderData ? "opacity-60" : ""}`}>
          {boons.map((boon) => (
            <BoonRow
              key={boon.id}
              troupeId={troupeId}
              boon={boon}
              characters={characters}
              open={open === boon.id}
              onToggle={() => setOpen(open === boon.id ? null : boon.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function BoonRow({
  troupeId,
  boon,
  characters,
  open,
  onToggle,
}: {
  troupeId: string;
  boon: BoonOut;
  characters: CharacterChoice[];
  open: boolean;
  onToggle: () => void;
}) {
  const dates = useDates();
  const state = stateText(boon);
  return (
    <li aria-label={`${owes(boon)}, ${kindName(boon.kind).toLowerCase()}`} className="rounded-lg border border-ash bg-dusk p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p>
            <span className="text-parchment">{partyName(boon.debtor)}</span>
            <span className="text-mist"> owes </span>
            <span className="text-parchment">{partyName(boon.creditor)}</span>
            <span className="text-mist"> · </span>
            <span className="text-gold">{kindName(boon.kind)}</span>
            <span className="text-mist"> · {dates.day(boon.made_on)}</span>
          </p>
          {boon.reason && <p className="text-mist">{boon.reason}</p>}
          {boon.conditions && <p className="text-xs text-mist">Conditions: {boon.conditions}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {state && <Badge tone={boon.state === "void" ? "blood" : "mist"}>{state}</Badge>}
          <Button variant="ghost" aria-expanded={open} onClick={onToggle}>
            {open ? "Close" : "Open"}
          </Button>
        </div>
      </div>
      {open && <BoonDetail troupeId={troupeId} boonId={boon.id} characters={characters} />}
    </li>
  );
}

type Doing = "edit" | "trade" | "pass" | "settle" | "void" | "reopen";

const ACTION_LABELS: Record<Doing, string> = {
  edit: "Edit",
  trade: "Trade",
  pass: "Pass on",
  settle: "Settle",
  void: "Make void",
  reopen: "Reopen",
};

function BoonDetail({ troupeId, boonId, characters }: { troupeId: string; boonId: string; characters: CharacterChoice[] }) {
  const dates = useDates();
  const [doing, setDoing] = useState<Doing | null>(null);
  const boon = useQuery({
    queryKey: ["boon", troupeId, boonId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/boons/{boon_id}", {
          params: { path: { troupe_id: troupeId, boon_id: boonId } },
        }),
      ),
  });
  if (boon.isPending) return <Loading />;
  if (boon.error) return <ErrorText error={boon.error} />;
  const b = boon.data;
  const done = () => setDoing(null);
  return (
    <div className="mt-3 flex flex-col gap-3 border-t border-ash pt-3">
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[auto_1fr]">
        <dt className="text-mist">Registered</dt>
        <dd>
          {dates.dateTime(b.submitted_at)}
          {b.submitted_by && <span className="text-mist"> by {b.submitted_by}</span>}
        </dd>
        {b.notify_on_trade && (
          <>
            <dt className="text-mist">If traded</dt>
            <dd>Its debtor&apos;s player is told</dd>
          </>
        )}
        {b.staff_note && (
          <>
            <dt className="text-mist">Staff note</dt>
            <dd className="whitespace-pre-line">{b.staff_note}</dd>
          </>
        )}
        {b.closed_at && (
          <>
            <dt className="text-mist">{b.state === "void" ? "Made void" : "Settled"}</dt>
            <dd>
              {dates.dateTime(b.closed_at)}
              {b.closed_note && <span className="text-mist"> · {b.closed_note}</span>}
            </dd>
          </>
        )}
      </dl>
      {doing === null ? (
        <div role="group" aria-label="What to do with it" className="flex flex-wrap gap-2">
          {actionsFor(b.state).map((a) => (
            <Button key={a} variant={a === "void" ? "ghost" : "secondary"} onClick={() => setDoing(a)}>
              {ACTION_LABELS[a]}
            </Button>
          ))}
        </div>
      ) : doing === "edit" ? (
        <EditForm troupeId={troupeId} boon={b} characters={characters} onDone={done} />
      ) : doing === "trade" || doing === "pass" ? (
        <MoveForm troupeId={troupeId} boon={b} characters={characters} pass={doing === "pass"} onDone={done} />
      ) : doing === "settle" ? (
        <SettleForm troupeId={troupeId} boon={b} onDone={done} />
      ) : (
        <NoteForm troupeId={troupeId} boon={b} action={doing} onDone={done} />
      )}
      <div>
        <h4 className="text-xs tracking-wide text-mist uppercase">Its log</h4>
        <ol aria-label={`Log of ${owes(b)}`} className="mt-1 flex flex-col gap-1 text-xs">
          {(b.events ?? []).map((e) => (
            <li key={e.id}>
              <span className="text-parchment">{eventName(e.kind)}</span>
              <span className="text-mist">
                {" "}
                · {dates.dateTime(e.at)}
                {e.by && ` · ${e.by}`}
                {e.as_character && ` as ${e.as_character}`}
              </span>
              {e.note && <span> · {e.note}</span>}
              {e.changes && e.changes.length > 0 && (
                <ul className="ml-3 text-mist">
                  {e.changes.map((c) => (
                    <li key={c.field}>{changeText(c)}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function FormButtons({ pending, ready, label, danger, onCancel }: { pending: boolean; ready: boolean; label: string; danger?: boolean; onCancel: () => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button type="submit" variant={danger ? "danger" : "primary"} disabled={pending || !ready}>
        {label}
      </Button>
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}

function boonPath(troupeId: string, boon: BoonOut) {
  return { params: { path: { troupe_id: troupeId, boon_id: boon.id } } };
}

function EditForm({ troupeId, boon, characters, onDone }: { troupeId: string; boon: BoonOut; characters: CharacterChoice[]; onDone: () => void }) {
  const [debtor, setDebtor] = useState(picked(boon.debtor));
  const [creditor, setCreditor] = useState(picked(boon.creditor));
  const [kind, setKind] = useState<BoonKind>(boon.kind);
  const [madeOn, setMadeOn] = useState(boon.made_on);
  const [reason, setReason] = useState(boon.reason);
  const [conditions, setConditions] = useState(boon.conditions);
  const [notify, setNotify] = useState(boon.notify_on_trade);
  const [staffNote, setStaffNote] = useState(boon.staff_note);
  const [note, setNote] = useState("");
  const d = partyIn(debtor.who, debtor.name);
  const c = partyIn(creditor.who, creditor.name);
  const save = useAction(async () => {
    if (!d || !c) return;
    await unwrap(
      api.PATCH("/api/troupes/{troupe_id}/boons/{boon_id}", {
        ...boonPath(troupeId, boon),
        body: {
          debtor: d,
          creditor: c,
          kind,
          made_on: madeOn,
          reason,
          conditions,
          notify_on_trade: notify,
          staff_note: staffNote,
          note,
        },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Edit: ${owes(boon)}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Debtor">
          <WhoPicker characters={characters} who={debtor.who} name={debtor.name} onChange={(who, name) => setDebtor({ who, name })} />
        </Field>
        <Field label="Creditor">
          <WhoPicker characters={characters} who={creditor.who} name={creditor.name} onChange={(who, name) => setCreditor({ who, name })} />
        </Field>
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value as BoonKind)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Date" hint="The in-game night it was made.">
          <DateInput required value={madeOn} onChange={(e) => setMadeOn(e.target.value)} />
        </Field>
      </div>
      <Field label="Reason">
        <Input maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="Conditions">
        <Input maxLength={2000} value={conditions} onChange={(e) => setConditions(e.target.value)} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
        Tell the debtor&apos;s player if it&apos;s traded
      </label>
      <Field label="Staff note" hint="For storytellers and assistant storytellers only.">
        <Textarea rows={2} maxLength={2000} value={staffNote} onChange={(e) => setStaffNote(e.target.value)} />
      </Field>
      <Field label="Why the edit" hint="Goes in its log. What changed shows only to storytellers and assistant storytellers.">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <FormButtons pending={save.isPending} ready={Boolean(d && c && madeOn && note.trim())} label="Save the edit" onCancel={onDone} />
    </form>
  );
}

/** A trade, which gives the boon to a new creditor; or a passing on of either side, such as to a broodmate after a death. */
function MoveForm({
  troupeId,
  boon,
  characters,
  pass,
  onDone,
}: {
  troupeId: string;
  boon: BoonOut;
  characters: CharacterChoice[];
  pass: boolean;
  onDone: () => void;
}) {
  const [side, setSide] = useState<"debtor" | "creditor">("debtor");
  const [to, setTo] = useState({ who: "", name: "" });
  const [note, setNote] = useState("");
  const target = partyIn(to.who, to.name);
  const save = useAction(async () => {
    if (!target) return;
    if (pass) {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/pass-on", {
          ...boonPath(troupeId, boon),
          body: { side, to: target, note },
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/trade", {
          ...boonPath(troupeId, boon),
          body: { creditor: target, note },
        }),
      );
    }
    onDone();
  });
  return (
    <form
      aria-label={pass ? `Pass on: ${owes(boon)}` : `Trade: ${owes(boon)}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {pass ? (
        <fieldset className="flex flex-wrap gap-4 text-sm">
          <legend className="mb-1 text-mist">Whose side passes on</legend>
          {(["debtor", "creditor"] as const).map((s) => (
            <label key={s} className="flex items-center gap-2">
              <input type="radio" name={`side-${boon.id}`} checked={side === s} onChange={() => setSide(s)} />
              {s === "debtor" ? `${boon.debtor.name}'s, the debtor's` : `${boon.creditor.name}'s, the creditor's`}
            </label>
          ))}
        </fieldset>
      ) : (
        <p className="text-sm text-mist">
          {boon.creditor.name} trades it: the new creditor holds it, and its log keeps the trade.
          {boon.notify_on_trade && " Its debtor's player is told."}
        </p>
      )}
      <Field label={pass ? "Passes on to" : "Traded to"}>
        <WhoPicker characters={characters} who={to.who} name={to.name} onChange={(who, name) => setTo({ who, name })} />
      </Field>
      <Field label="Note (optional)">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <FormButtons pending={save.isPending} ready={Boolean(target)} label={pass ? "Pass it on" : "Record the trade"} onCancel={onDone} />
    </form>
  );
}

function SettleForm({ troupeId, boon, onDone }: { troupeId: string; boon: BoonOut; onDone: () => void }) {
  const [how, setHow] = useState<SettledHow>("called_in");
  const [note, setNote] = useState("");
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/settle", {
        ...boonPath(troupeId, boon),
        body: { how, note },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Settle: ${owes(boon)}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <fieldset className="flex flex-col gap-2 text-sm">
        <legend className="mb-1 text-mist">How it was settled</legend>
        {SETTLED.map((s) => (
          <label key={s.value} className="flex items-start gap-2">
            <input type="radio" className="mt-1" name={`how-${boon.id}`} checked={how === s.value} onChange={() => setHow(s.value)} />
            <span>
              {s.label}
              <span className="block text-xs text-mist">{s.meaning}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <Field label="Note (optional)" hint="What it was called in for, say.">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <FormButtons pending={save.isPending} ready label="Settle it" onCancel={onDone} />
    </form>
  );
}

function NoteForm({ troupeId, boon, action, onDone }: { troupeId: string; boon: BoonOut; action: "void" | "reopen"; onDone: () => void }) {
  const [note, setNote] = useState("");
  const save = useAction(async () => {
    const path = boonPath(troupeId, boon);
    if (action === "void")
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/void", {
          ...path,
          body: { note },
        }),
      );
    else
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/reopen", {
          ...path,
          body: { note },
        }),
      );
    onDone();
  });
  return (
    <form
      aria-label={`${ACTION_LABELS[action]}: ${owes(boon)}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label="Why" hint={action === "void" ? "Entered by mistake, say. It stays in the ledger as void." : "It stands again: settled by mistake, say."}>
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <FormButtons
        pending={save.isPending}
        ready={Boolean(note.trim())}
        label={action === "void" ? "Make it void" : "Reopen it"}
        danger={action === "void"}
        onCancel={onDone}
      />
    </form>
  );
}

/**
 * Register boons: one, or a whole game's at once. Each row is a boon, made as many
 * times as its count ("1 of 3", "2 of 3"...); rows left untouched are skipped. All
 * register together, or none do.
 */
function QuickEntry({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const dates = useDates();
  const toast = useToast();
  const [madeOn, setMadeOn] = useState(today(dates));
  const [rows, setRows] = useState<EntryRow[]>([emptyRow(today(dates))]);
  const [note, setNote] = useState("");
  const [gameId, setGameId] = useState("");
  // The troupe's recent games, for the statistics' activity per game (#702).
  const games = useQuery({
    queryKey: ["boon-games", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-games", { params: { path: { troupe_id: troupeId } } })),
  });
  const set = (i: number, change: Partial<EntryRow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const started = rows.filter(rowStarted);
  const parts = started.map((r) => ({
    row: r,
    debtor: partyIn(r.debtor.who, r.debtor.name),
    creditor: partyIn(r.creditor.who, r.creditor.name),
  }));
  const ready = parts.length > 0 && parts.every((p) => p.debtor && p.creditor && p.row.made_on);
  const total = rowsTotal(rows);
  const save = useAction(async () => {
    const body = parts.map(({ row, debtor, creditor }) => ({
      debtor: debtor!,
      creditor: creditor!,
      kind: row.kind,
      made_on: row.made_on,
      reason: row.reason,
      conditions: row.conditions,
      notify_on_trade: row.notify_on_trade,
      staff_note: "",
      count: Math.max(1, row.count || 1),
    }));
    const made = await unwrap(
      api.POST("/api/troupes/{troupe_id}/boons", {
        params: { path: { troupe_id: troupeId } },
        body: { boons: body, note, game_id: gameId || null },
      }),
    );
    toast({
      message: made.length === 1 ? "Registered a boon." : `Registered ${made.length} boons.`,
    });
    onDone();
  });
  return (
    <form
      aria-label="Register boons"
      className="mt-3 flex flex-col gap-3 border-t border-ash pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Date for new rows" hint="The in-game night: each row can have its own.">
          <DateInput
            value={madeOn}
            onChange={(e) => {
              const next = e.target.value;
              // Rows still on the old date move with it.
              setRows(rows.map((r) => (r.made_on === madeOn ? { ...r, made_on: next } : r)));
              setMadeOn(next);
            }}
          />
        </Field>
        <Field label="Where they come from (optional)" hint="Goes in each boon's log: “Elysium, 3 October”.">
          <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {(games.data?.length ?? 0) > 0 && (
          <Field label="At a game (optional)" hint="The game they were made at, for the statistics' boons at each game.">
            <Select value={gameId} onChange={(e) => setGameId(e.target.value)}>
              <option value="">Not at a game</option>
              {games.data!.map((g) => (
                <option key={g.id} value={g.id}>
                  {dates.dateTime(g.starts_at)}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </div>
      <ol className="flex flex-col gap-3">
        {rows.map((row, i) => (
          <li key={i} aria-label={`Boon ${i + 1}`} className="flex flex-col gap-2 rounded-md border border-ash p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Debtor" hint="Who owes it.">
                <WhoPicker characters={characters} who={row.debtor.who} name={row.debtor.name} onChange={(who, name) => set(i, { debtor: { who, name } })} />
              </Field>
              <Field label="Creditor" hint="Who it's owed to.">
                <WhoPicker
                  characters={characters}
                  who={row.creditor.who}
                  name={row.creditor.name}
                  onChange={(who, name) => set(i, { creditor: { who, name } })}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-[1fr_1fr_6rem]">
              <Field label="Kind">
                <Select value={row.kind} onChange={(e) => set(i, { kind: e.target.value as BoonKind })}>
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Date">
                <DateInput required value={row.made_on} onChange={(e) => set(i, { made_on: e.target.value })} />
              </Field>
              <Field label="How many">
                <Input type="number" min={1} max={20} value={row.count} onChange={(e) => set(i, { count: Number(e.target.value) })} />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Reason">
                <Input maxLength={2000} value={row.reason} onChange={(e) => set(i, { reason: e.target.value })} />
              </Field>
              <Field label="Conditions">
                <Input maxLength={2000} value={row.conditions} placeholder="Cannot be traded" onChange={(e) => set(i, { conditions: e.target.value })} />
              </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={row.notify_on_trade} onChange={(e) => set(i, { notify_on_trade: e.target.checked })} />
                Tell the debtor&apos;s player if it&apos;s traded
              </label>
              {rows.length > 1 && (
                <Button type="button" variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                  Remove
                </Button>
              )}
            </div>
          </li>
        ))}
      </ol>
      <div>
        <Button type="button" variant="secondary" onClick={() => setRows([...rows, emptyRow(madeOn)])}>
          Add a row
        </Button>
      </div>
      <ErrorText error={save.error} />
      <FormButtons pending={save.isPending} ready={ready} label={total <= 1 ? "Register the boon" : `Register ${total} boons`} onCancel={onDone} />
    </form>
  );
}
