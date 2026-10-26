import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { ExpendableOut, GameOut, InfluenceDetailsIn, InfluenceStandingOut, PlayView } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction, usePreferences } from "../../hooks";
import { offered, reachNote, TYPE_NAMES } from "../../influence";
import { Derangements, showsDerangements } from "./Derangements";
import { Feed, FeedButton } from "./Feed";
import { PoolsTab, SheetTab } from "./ReferenceTabs";
import { incapacitated, influenceStanding, latestUndoable, type Damage, type Shown, type ShownEntry } from "./tracker";
import { usePlay, type Sync } from "./usePlay";
import { useReference } from "./useReference";
import { useWakeLock } from "./wakeLock";

type Change = { tracker: string; amount: number; damage?: Damage; label: string };
type RecordTap = (change: Change) => void;

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const TABS = [
  { key: "sheet", label: "Sheet" },
  { key: "tracker", label: "Tracker" },
  { key: "pools", label: "Pools" },
] as const;
type Tab = (typeof TABS)[number]["key"];

/**
 * A living sheet for a game, laid out for a phone in one hand, in three tabs:
 * the Sheet to look things up in; the Tracker, with blood, Willpower, health,
 * Morality and Beast traits as big boxes to tap, the character's limited uses
 * and the game's log with Undo; and Pools, its test pools and powers. Taps are
 * kept on the phone when there is no signal and sent when it returns. The
 * Sheet and Pools load once, when the page opens, so the tabs switch at once.
 * The person's settings choose the tab it opens on, whether quick notes start
 * on, and whether the screen stays awake while it is open.
 */
export function PlayPage() {
  const { characterId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const prefs = usePreferences();
  const tab: Tab = TABS.find((t) => t.key === params.get("tab"))?.key ?? prefs.play_tab;
  const { view, shown, tap, sync, accept } = usePlay(characterId);
  const { reference, error: referenceError } = useReference(characterId);
  // Quick notes start as the settings say; the switch changes them for this visit.
  const [quickNotes, setQuickNotes] = useState(prefs.quick_notes);
  const awake = useWakeLock(prefs.keep_awake);
  const [asking, setAsking] = useState<Change | null>(null);
  const [spending, setSpending] = useState<Change | null>(null);
  // An influence spend in the game's log whose details are being added or changed.
  const [detailing, setDetailing] = useState<ShownEntry | null>(null);
  // The Feed sheet is open (the timer itself is kept by Feed, on the device).
  const [feeding, setFeeding] = useState(false);
  const choose = (next: Tab) =>
    setParams(
      (p) => {
        p.set("tab", next);
        return p;
      },
      { replace: true },
    );
  const tabs = <TabBar tab={tab} onChange={choose} />;

  if (view.isPending) return <PlayShell characterId={characterId} sync={sync} awake={awake} tabs={tabs}><p className="py-8 text-center text-mist">Loading…</p></PlayShell>;
  if (!shown) return <PlayShell characterId={characterId} sync={sync} awake={awake} tabs={tabs}><ErrorText error={view.error} /></PlayShell>;

  const record: RecordTap = (change) => {
    // Influence always asks for the spend's details, for the troupe's influence log.
    if (change.amount < 0 && influenceStanding(shown, change.tracker)) setSpending(change);
    // Quick notes ask what a spend was for; restoring needs no reason.
    else if (quickNotes && change.amount < 0) setAsking(change);
    else tap({ kind: "change", tracker: change.tracker, amount: change.amount, damage: change.damage ?? null });
  };
  const lookup = (show: (r: NonNullable<typeof reference>) => ReactNode) =>
    reference ? show(reference) : referenceError ? <ErrorText error={referenceError} /> : <p className="py-8 text-center text-mist">Loading…</p>;

  return (
    <PlayShell characterId={characterId} sync={sync} awake={awake} name={shown.character_name} tabs={tabs}>
      <Identity view={shown} />
      {tab === "sheet" && lookup((r) => <SheetTab reference={r} />)}
      {tab === "pools" && lookup((r) => <PoolsTab reference={r} willpower={shown.willpower.value} />)}
      {tab === "tracker" && (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <BoxTracker
              title="Blood"
              tracker="blood"
              value={shown.blood.value}
              most={shown.blood.most}
              hint={`${shown.blood_per_turn} a turn${shown.half_blood ? " · Half Blood: fed short last downtime" : ""}`}
              record={record}
              extra={<FeedButton onClick={() => setFeeding(true)} />}
            />
            <BoxTracker title="Willpower" tracker="willpower" value={shown.willpower.value} most={shown.willpower.most} record={record} />
            <HealthTracker view={shown} record={record} />
            <div className="grid gap-3">
              {shown.morality && (
                <BoxTracker
                  title={shown.morality.name}
                  tracker="morality"
                  value={shown.morality.value}
                  most={shown.morality.rating}
                  hint={shown.morality.value < shown.morality.rating ? "A lost dot goes on the sheet through your storytellers." : undefined}
                  record={record}
                  small
                />
              )}
              <BoxTracker
                title="Beast traits"
                tracker="beast"
                value={shown.beast.value}
                most={shown.beast.most}
                spendIsUp
                hint={shown.beast.value >= shown.beast.most ? `Five Beast traits: a dot of ${shown.morality?.name ?? "Morality"} is lost.` : undefined}
                record={record}
                small
              />
              <Derangements view={shown} record={record} tap={tap} />
            </div>
          </div>
          <Expendables view={shown} record={record} quickNotes={quickNotes} setQuickNotes={setQuickNotes} online={sync.online} onChange={accept} />
          <Notes add={(note) => tap({ kind: "note", note })} />
          <GameLog view={shown} undo={(entry) => tap({ kind: "undo", undoes: entry.id })} onDetails={sync.online ? setDetailing : undefined} />
          <ResetGame view={shown} sync={sync} onReset={accept} />
          <PastGames characterId={characterId} current={shown.game?.id} />
        </>
      )}
      <Feed view={shown} asking={feeding} onClose={() => setFeeding(false)} tap={tap} />
      {spending && (
        <InfluenceSheet
          standing={influenceStanding(shown, spending.tracker)!}
          left={shown.expendables.find((e) => e.key === spending.tracker)?.left ?? 1}
          onCancel={() => setSpending(null)}
          onSave={(details, times) => {
            tap({ kind: "change", tracker: spending.tracker, amount: -times, influence: details });
            setSpending(null);
          }}
        />
      )}
      {detailing?.influence && <DetailsLater view={shown} entry={detailing} onDone={() => setDetailing(null)} onChange={accept} />}
      {asking && (
        <NoteSheet
          change={asking}
          onCancel={() => setAsking(null)}
          onSave={(note) => {
            tap({ kind: "change", tracker: asking.tracker, amount: asking.amount, damage: asking.damage ?? null, note });
            setAsking(null);
          }}
        />
      )}
    </PlayShell>
  );
}

/** The page around the sheet: back to the character, whether the screen is kept awake and taps are saved, and the tabs. */
function PlayShell({
  characterId,
  sync,
  awake,
  name,
  tabs,
  children,
}: {
  characterId: string;
  sync: Sync;
  awake: boolean;
  name?: string;
  tabs: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link to={`/characters/${characterId}`} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
            ← {name ?? "Back"}
          </Link>
          <span className="flex items-start gap-2">
            {awake && (
              <span className="rounded-full border border-ash px-2.5 py-0.5 text-xs whitespace-nowrap text-mist" title="Kept on while the Play View is open, as your settings ask.">
                ☀ Screen awake
              </span>
            )}
            <SyncStatus sync={sync} />
          </span>
        </div>
        {tabs}
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-3 px-4 pt-3">{children}</main>
    </div>
  );
}

/** Sheet, Tracker and Pools: three big tabs across the top, for a thumb. */
function TabBar({ tab, onChange }: { tab: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="mx-auto grid max-w-3xl grid-cols-3 px-2" role="tablist" aria-label="Play View">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={tab === t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "min-h-11 border-b-2 text-sm font-medium tracking-wide",
            tab === t.key ? "border-gold text-gold" : "border-transparent text-mist hover:text-parchment",
          )}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export function SyncStatus({ sync }: { sync: Sync }) {
  const waiting = sync.waiting === 1 ? "1 tap waiting" : `${sync.waiting} taps waiting`;
  const text = !sync.online ? (sync.waiting ? `Offline · ${waiting}` : "Offline") : sync.waiting ? `Saving · ${waiting}` : "Saved";
  return (
    <span role="status" className="flex flex-col items-end gap-1 text-right">
      <span
        className={cx(
          "rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap",
          !sync.online ? "border-blood text-blood-bright" : sync.waiting ? "border-gold/50 text-gold" : "border-ash text-mist",
        )}
      >
        {text}
      </span>
      {sync.error && <span className="text-xs text-blood-bright">{sync.error}</span>}
    </span>
  );
}

function Identity({ view }: { view: PlayView }) {
  const facts = [view.clan, view.sect, view.generation ? `Generation ${view.generation}` : null, `${view.blood_per_turn} blood a turn`].filter(Boolean);
  return (
    <section className="flex items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl leading-tight">{view.character_name}</h1>
        <p className="text-sm text-mist">{facts.join(" · ")}</p>
      </div>
      <p className="text-right text-xs text-mist">
        {view.kind === "npc" ? "NPC" : view.player_name}
        <br />
        {view.game ? `Game ${view.game.number}` : "First game"}
      </p>
    </section>
  );
}

function Panel({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-base text-gold">{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  );
}

/** A big round button for one thumb. */
function TapButton({ label, children, onClick, disabled, tone = "plain" }: { label: string; children: ReactNode; onClick: () => void; disabled?: boolean; tone?: "plain" | "blood" }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "grid h-12 min-w-12 place-items-center rounded-full border px-3 text-lg font-semibold transition-colors active:scale-95 disabled:opacity-35",
        tone === "blood" ? "border-blood bg-blood text-parchment hover:bg-blood-bright" : "border-ash bg-night text-parchment hover:border-mist",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Boxes to the tracker's most, filled up to its value. Tapping a filled box
 * spends one, an empty box restores one; the buttons do the same.
 */
function BoxTracker({
  title,
  tracker,
  value,
  most,
  hint,
  record,
  small,
  spendIsUp,
  extra,
}: {
  title: string;
  tracker: string;
  value: number;
  most: number;
  hint?: string;
  record: RecordTap;
  small?: boolean;
  /** Beast traits are gained rather than spent: "+" adds one. */
  spendIsUp?: boolean;
  /** Another button beside − and + (Feed, by Blood). */
  extra?: ReactNode;
}) {
  const down = () => record({ tracker, amount: -1, label: title });
  const up = () => record({ tracker, amount: 1, label: title });
  return (
    <Panel
      title={title}
      actions={
        <span className="font-display text-2xl text-parchment" aria-label={`${title}: ${value} of ${most}`}>
          {value}
          <span className="text-base text-mist"> / {most}</span>
        </span>
      }
    >
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={`${title} boxes`}>
        {Array.from({ length: most }, (_, i) => (
          <button
            key={i}
            type="button"
            aria-label={i < value ? `Spend ${title}` : `Restore ${title}`}
            tabIndex={-1}
            onClick={i < value ? down : up}
            className={cx(
              "rounded-md border transition-colors",
              small ? "h-9 w-9" : "h-10 w-10",
              i < value ? (tracker === "blood" ? "border-blood bg-blood" : "border-gold/70 bg-gold/70") : "border-ash bg-night",
            )}
          />
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-xs text-mist">{hint}</span>
        <span className="flex gap-2">
          {extra}
          <TapButton label={spendIsUp ? `Remove a ${title} point` : `Spend ${title}`} onClick={down} disabled={value <= 0} tone={spendIsUp ? "plain" : "blood"}>
            −
          </TapButton>
          <TapButton label={spendIsUp ? `Gain a ${title} point` : `Restore ${title}`} onClick={up} disabled={value >= most} tone={spendIsUp ? "blood" : "plain"}>
            +
          </TapButton>
        </span>
      </div>
    </Panel>
  );
}

/** Healthy, Injured and Incapacitated boxes, filled in the order damage came. */
function HealthTracker({ view, record }: { view: PlayView; record: RecordTap }) {
  const marks = view.health.marks;
  const total = view.health.levels.reduce((sum, l) => sum + l.boxes, 0);
  let offset = 0;
  const has = (kind: Damage) => marks.includes(kind);
  const damage = (kind: Damage, amount: number) =>
    record({ tracker: "health", amount, damage: kind, label: amount > 0 ? `${kind} damage` : `heal ${kind}` });
  return (
    <Panel title="Health">
      <ul className="flex flex-col gap-2">
        {view.health.levels.map((level) => {
          const start = offset;
          offset += level.boxes;
          return (
            <li key={level.name} className="flex items-center justify-between gap-2">
              <span className="w-28 text-sm">{level.name}</span>
              <span className="flex flex-1 flex-wrap justify-end gap-1.5">
                {Array.from({ length: level.boxes }, (_, i) => {
                  const mark = marks[start + i];
                  return (
                    <span
                      key={i}
                      aria-label={mark ? `${mark} damage` : "unmarked"}
                      className={cx(
                        "grid h-9 w-9 place-items-center rounded-md border text-lg leading-none",
                        mark === "aggravated" ? "border-blood bg-blood text-parchment" : mark === "normal" ? "border-mist bg-ash text-parchment" : "border-ash bg-night",
                      )}
                    >
                      {mark === "aggravated" ? "✕" : mark === "normal" ? "/" : ""}
                    </span>
                  );
                })}
              </span>
            </li>
          );
        })}
      </ul>
      {incapacitated(view) && (
        <p className="mt-2 rounded-md border border-blood/60 bg-blood/15 px-3 py-2 text-sm">
          {view.health.stamina_focus ? "Incapacitated, but a Stamina focus spares you the penalty." : "Incapacitated characters lose their simple action."}
        </p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Button variant="danger" className="min-h-12" disabled={marks.length >= total} onClick={() => damage("normal", 1)}>
          + Normal
        </Button>
        <Button variant="danger" className="min-h-12" disabled={marks.length >= total} onClick={() => damage("aggravated", 1)}>
          + Aggravated
        </Button>
        <Button variant="secondary" className="min-h-12" disabled={!has("normal")} onClick={() => damage("normal", -1)}>
          Heal normal
        </Button>
        <Button variant="secondary" className="min-h-12" disabled={!has("aggravated")} onClick={() => damage("aggravated", -1)}>
          Heal aggravated
        </Button>
      </div>
    </Panel>
  );
}

/** Uses a game: backgrounds, merits and powers the rules limit, and the player's own counters. */
function Expendables({
  view,
  record,
  quickNotes,
  setQuickNotes,
  online,
  onChange,
}: {
  view: PlayView;
  record: RecordTap;
  quickNotes: boolean;
  setQuickNotes: (on: boolean) => void;
  online: boolean;
  onChange: (view: PlayView) => Promise<void>;
}) {
  const path = { params: { path: { character_id: view.character_id } } };
  const [form, setForm] = useState({ name: "", uses: 3 });
  const add = useAction(async () => {
    await onChange(await unwrap(api.POST("/api/characters/{character_id}/play/counters", { ...path, body: form })));
    setForm({ name: "", uses: 3 });
  });
  const remove = useAction(async (counterId: string) =>
    onChange(
      await unwrap(
        api.DELETE("/api/characters/{character_id}/play/counters/{counter_id}", {
          params: { path: { character_id: view.character_id, counter_id: counterId } },
        }),
      ),
    ),
  );
  return (
    <Panel
      title="Uses this game"
      actions={
        <label className="flex min-h-10 items-center gap-2 text-sm text-mist">
          <input type="checkbox" className="h-5 w-5 accent-[var(--color-gold)]" checked={quickNotes} onChange={(e) => setQuickNotes(e.target.checked)} />
          Quick notes
        </label>
      }
    >
      {view.expendables.length === 0 && <p className="text-sm text-mist">Nothing on this sheet is limited to so many uses a game.</p>}
      <ul className="divide-y divide-ash">
        {view.expendables.map((e) => (
          <ExpendableRow key={e.key} item={e} record={record} onRemove={e.counter_id && online ? () => remove.mutate(e.counter_id!) : undefined} />
        ))}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-end gap-2 border-t border-ash pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined);
        }}
      >
        <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-mist">
          Your own counter
          <Input placeholder="Fetish charges" value={form.name} required maxLength={80} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-mist">
          Uses
          <Input type="number" min={1} max={99} required value={form.uses} onChange={(e) => setForm({ ...form, uses: Number(e.target.value) })} className="w-20" />
        </label>
        <Button type="submit" variant="secondary" disabled={!online || add.isPending}>
          Add counter
        </Button>
        {!online && <span className="w-full text-xs text-mist">Adding a counter needs a connection.</span>}
      </form>
      <ErrorText error={add.error ?? remove.error} />
    </Panel>
  );
}

function ExpendableRow({ item, record, onRemove }: { item: ExpendableOut; record: RecordTap; onRemove?: () => void }) {
  const label = item.detail ? `${item.name}: ${item.detail}` : item.name;
  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-parchment">{label}</p>
        <p className="text-xs text-mist">
          {item.group} · {item.left} of {item.uses} left
          {item.owed > 0 && ` · ${item.owed} spent at earlier games this month`}
          {onRemove && (
            <button type="button" onClick={onRemove} className="ml-2 underline hover:text-parchment" aria-label={`Remove the counter ${label}`}>
              remove
            </button>
          )}
        </p>
      </div>
      {/* Influence comes back only by undoing its spend, which takes it off the influence log too. */}
      {!item.influence && (
        <TapButton label={`Restore ${label}`} onClick={() => record({ tracker: item.key, amount: 1, label })} disabled={item.left >= item.uses}>
          +
        </TapButton>
      )}
      <Button className="min-h-12 min-w-20" onClick={() => record({ tracker: item.key, amount: -1, label })} disabled={item.left <= 0} aria-label={`Use ${label}`}>
        Use
      </Button>
    </li>
  );
}

/** A one-line note for a spend, in quick note mode. */
function NoteSheet({ change, onSave, onCancel }: { change: Change; onSave: (note: string) => void; onCancel: () => void }) {
  const [note, setNote] = useState("");
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gold/50 bg-dusk p-4 shadow-2xl" role="dialog" aria-label="Note for this spend">
      <form
        className="mx-auto flex max-w-3xl flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(note);
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          What was {change.label} for? (optional)
          <Input autoFocus maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder="got the Prince's itinerary" />
        </label>
        <div className="flex gap-2">
          <Button type="submit" className="min-h-12 flex-1">
            Save
          </Button>
          <Button type="button" variant="ghost" className="min-h-12" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

type Fields = { specialization: string; action: string; purpose: string };

/** The specialisation, action and purpose of an influence spend. Only actions the character can reach are offered. */
function DetailFields({ standing, fields, onChange }: { standing: InfluenceStandingOut; fields: Fields; onChange: (fields: Fields) => void }) {
  const actions = offered(standing, fields.specialization);
  const action = standing.actions.find((a) => a.key === fields.action);
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-sm">
          Specialisation
          <Select
            value={fields.specialization}
            onChange={(e) => {
              const specialization = e.target.value;
              // An action out of reach without the specialisation is chosen again.
              const kept = offered(standing, specialization).some((a) => a.key === fields.action);
              onChange({ ...fields, specialization, action: kept ? fields.action : "" });
            }}
          >
            <option value="">None</option>
            {standing.held.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Action
          <Select value={fields.action} onChange={(e) => onChange({ ...fields, action: e.target.value })}>
            <option value="">Choose…</option>
            {actions.map((a) => (
              <option key={a.key} value={a.key}>
                {a.label}
              </option>
            ))}
          </Select>
        </label>
      </div>
      {reachNote(standing, fields.specialization, action) && <p className="text-xs text-mist">{reachNote(standing, fields.specialization, action)}</p>}
      <label className="flex flex-col gap-1 text-sm">
        Purpose
        <Input maxLength={300} value={fields.purpose} onChange={(e) => onChange({ ...fields, purpose: e.target.value })} placeholder="To secure the Weather" />
      </label>
    </>
  );
}

function asDetails(fields: Fields): InfluenceDetailsIn {
  return { specialization: fields.specialization, action: fields.action, purpose: fields.purpose.trim() };
}

/**
 * Spending influence: what it was for, for the troupe's influence log, and how
 * many uses it took. Skip details spends it all the same, logged as needing
 * them, so a loud room never waits on typing.
 */
function InfluenceSheet({
  standing,
  left,
  onSave,
  onCancel,
}: {
  standing: InfluenceStandingOut;
  left: number;
  onSave: (details: InfluenceDetailsIn | null, times: number) => void;
  onCancel: () => void;
}) {
  const [fields, setFields] = useState<Fields>({ specialization: "", action: "", purpose: "" });
  const [times, setTimes] = useState(1);
  const type = TYPE_NAMES[standing.type];
  const ready = !!fields.action && !!fields.purpose.trim();
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 max-h-[90vh] overflow-y-auto border-t border-gold/50 bg-dusk p-4 shadow-2xl" role="dialog" aria-label={`Spend ${type} influence`}>
      <form
        className="mx-auto flex max-w-3xl flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) onSave(asDetails(fields), times);
        }}
      >
        <p className="text-sm font-medium">Spend {type} influence</p>
        <DetailFields standing={standing} fields={fields} onChange={setFields} />
        <label className="flex items-center gap-2 text-sm">
          Times
          <Input
            type="number"
            className="w-20"
            min={1}
            max={Math.max(1, left)}
            value={times}
            onChange={(e) => setTimes(Math.min(Math.max(1, Number(e.target.value) || 1), Math.max(1, left)))}
          />
          <span className="text-xs text-mist">{left === 1 ? "1 use left" : `${left} uses left`}</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" className="min-h-12 flex-1" disabled={!ready}>
            Spend
          </Button>
          <Button type="button" variant="secondary" className="min-h-12" onClick={() => onSave(null, times)}>
            Skip details
          </Button>
          <Button type="button" variant="ghost" className="min-h-12" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

/** Adding or changing a spend's details from the game's log, until the game ends. */
function DetailsLater({ view, entry, onDone, onChange }: { view: Shown; entry: ShownEntry; onDone: () => void; onChange: (view: PlayView) => Promise<void> }) {
  const spent = entry.influence!;
  const standing = view.influence.find((s) => s.type === spent.type);
  const [fields, setFields] = useState<Fields>({ specialization: spent.specialization, action: spent.action_key ?? "", purpose: spent.purpose });
  const save = useAction(async () => {
    const data = await unwrap(
      api.PUT("/api/characters/{character_id}/play/taps/{tap_id}/influence", {
        params: { path: { character_id: view.character_id, tap_id: entry.id } },
        body: asDetails(fields),
      }),
    );
    await onChange(data);
    onDone();
  });
  if (!standing) return null;
  const type = TYPE_NAMES[standing.type];
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 max-h-[90vh] overflow-y-auto border-t border-gold/50 bg-dusk p-4 shadow-2xl" role="dialog" aria-label={`Details of ${spent.short_id}`}>
      <form
        className="mx-auto flex max-w-3xl flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <p className="text-sm font-medium">
          {type} influence spent{spent.times > 1 ? `, ${spent.times} times` : ""} ({spent.short_id})
        </p>
        <DetailFields standing={standing} fields={fields} onChange={setFields} />
        <div className="flex gap-2">
          <Button type="submit" className="min-h-12 flex-1" disabled={!fields.action || save.isPending}>
            Save details
          </Button>
          <Button type="button" variant="ghost" className="min-h-12" onClick={onDone}>
            Cancel
          </Button>
        </div>
        <ErrorText error={save.error} />
      </form>
    </div>
  );
}

function Notes({ add }: { add: (note: string) => void }) {
  const [note, setNote] = useState("");
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!note.trim()) return;
        add(note);
        setNote("");
      }}
    >
      <Input aria-label="A note for this game" placeholder="A note for this game…" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} className="flex-1" />
      <Button type="submit" variant="secondary" disabled={!note.trim()}>
        Add note
      </Button>
    </form>
  );
}

export function LogEntries({ log, onDetails }: { log: ShownEntry[]; onDetails?: (entry: ShownEntry) => void }) {
  const dates = useDates();
  if (log.length === 0) return <p className="text-sm text-mist">Nothing yet. Every tap shows here, newest first.</p>;
  return (
    <ol className="divide-y divide-ash text-sm">
      {log.map((e) => (
        <li key={e.id} className="flex gap-3 py-1.5">
          <time className="w-16 shrink-0 text-xs text-mist" dateTime={e.happened_at}>
            {dates.time(e.happened_at)}
          </time>
          <div className="min-w-0 flex-1">
            <p className={cx(e.undone && "text-mist line-through")}>
              {e.text}
              {e.pending && <span className="ml-2 text-xs text-gold">waiting</span>}
            </p>
            {e.note && <p className={cx("text-mist", e.undone && "line-through")}>“{e.note}”</p>}
            {e.by_staff && <p className="text-xs text-mist">by {e.actor_name}</p>}
            {e.influence && !e.undone && onDetails && (
              <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => onDetails(e)}>
                {e.influence.needs_details ? `Add details to ${e.influence.short_id}` : `Change details of ${e.influence.short_id}`}
              </button>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function GameLog({ view, undo, onDetails }: { view: Shown; undo: (entry: ShownEntry) => void; onDetails?: (entry: ShownEntry) => void }) {
  const last = latestUndoable(view.log);
  // Undoing a spend takes its entry off the influence log; if staff have changed it there, ask first.
  const [checking, setChecking] = useState<ShownEntry | null>(null);
  return (
    <Panel
      title="This game"
      actions={
        <Button
          variant="secondary"
          disabled={!last}
          onClick={() => last && (last.influence?.changed_by_staff ? setChecking(last) : undo(last))}
          aria-label={last ? `Undo ${last.text}` : "Undo"}
        >
          Undo
        </Button>
      }
    >
      {checking && (
        <div className="mb-3 flex flex-col gap-2 rounded-md border border-blood/60 bg-blood/15 p-3 text-sm" role="alertdialog" aria-label="Undo a changed spend">
          <p>
            Staff have changed {checking.influence?.short_id} in the influence log since it was spent. Undoing it takes it off the log, with their changes.
          </p>
          <div className="flex gap-2">
            <Button
              variant="danger"
              onClick={() => {
                undo(checking);
                setChecking(null);
              }}
            >
              Undo anyway
            </Button>
            <Button variant="ghost" onClick={() => setChecking(null)}>
              Keep it
            </Button>
          </div>
        </div>
      )}
      <LogEntries log={view.log} onDetails={onDetails} />
    </Panel>
  );
}

export function ResetGame({ view, sync, onReset }: { view: Shown; sync: Sync; onReset: (view: PlayView) => Promise<void> }) {
  const [asking, setAsking] = useState(false);
  const reset = useAction(async () => {
    const data = await unwrap(
      api.POST("/api/characters/{character_id}/play/reset", { params: { path: { character_id: view.character_id } }, body: { game_id: view.game?.id ?? null } }),
    );
    await onReset(data);
    setAsking(false);
  });
  const ready = sync.online && sync.waiting === 0;
  return (
    <section className="rounded-lg border border-ash p-3">
      {asking ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm">
            Put every tracker back for the next game? Blood to {view.blood.start}, Willpower to {view.willpower.start}, health clear and every use back.
            {showsDerangements(view) && ` Derangement traits stay at ${view.derangements.value}.`} This game's log is kept.
          </p>
          <div className="flex gap-2">
            <Button variant="danger" className="min-h-12 flex-1" disabled={reset.isPending || !ready} onClick={() => reset.mutate(undefined)}>
              Reset for next game
            </Button>
            <Button variant="ghost" className="min-h-12" onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="secondary" className="min-h-12 w-full" onClick={() => setAsking(true)} disabled={!ready}>
          Reset for next game…
        </Button>
      )}
      {!ready && <p className="mt-2 text-xs text-mist">Resetting waits until every tap is saved.</p>}
      <ErrorText error={reset.error} />
    </section>
  );
}

/** Games already over, each with its log, kept for the next downtime. */
function PastGames({ characterId, current }: { characterId: string; current: string | undefined }) {
  const games = useQuery({
    queryKey: ["play-games", characterId, current],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play/games", { params: { path: { character_id: characterId } } })),
  });
  if (!games.data?.length) return null;
  return (
    <Panel title="Past games">
      <ul className="divide-y divide-ash">
        {games.data.map((g) => (
          <PastGame key={g.id} characterId={characterId} game={g} />
        ))}
      </ul>
    </Panel>
  );
}

function PastGame({ characterId, game }: { characterId: string; game: GameOut }) {
  const [open, setOpen] = useState(false);
  const dates = useDates();
  const log = useQuery({
    queryKey: ["play-game", game.id],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/play/games/{game_id}", { params: { path: { character_id: characterId, game_id: game.id } } })),
    enabled: open,
  });
  const taps = game.taps === 1 ? "1 tap" : `${game.taps} taps`;
  const notes = game.notes === 1 ? "1 note" : `${game.notes} notes`;
  return (
    <li className="py-1">
      <button type="button" className="flex min-h-10 w-full items-center justify-between gap-2 text-left text-sm" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>
          Game {game.number} · {dates.date(game.started_at)}
        </span>
        <span className="text-xs text-mist">
          {taps}, {notes} {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (log.data ? <LogEntries log={log.data.log} /> : <p className="text-sm text-mist">Loading…</p>)}
    </li>
  );
}
