/** Targets of Attacks, Defends, Boosts and Blocks in the influence log, resolving them, and the effects they make (backend: horatio.influence_effects). */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { InfluenceChoicesOut, InfluenceEffectOut, InfluenceEntryOut, InfluenceTargetIn } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { TYPE_NAMES, type InfluenceType } from "../../influence";
import { costText, lastsText, targeted } from "../../influenceEffects";

export type TargetForm = {
  /** "c:<character id>", "entry" for an Attack on a log entry, or "" (a Defend's own character). */
  who: string;
  entry: string;
  type: "" | InfluenceType;
  activity: string;
};

export function targetForm(entry?: InfluenceEntryOut): TargetForm {
  const t = entry?.target;
  return {
    who: t?.character_id ? `c:${t.character_id}` : t?.entry_short_id ? "entry" : "",
    entry: t?.entry_short_id ?? "",
    type: t?.type && t.type !== entry?.type ? t.type : "",
    activity: t?.activity ?? "",
  };
}

/** The target to send for an action, or null for one that takes none. */
export function targetBody(form: TargetForm, actionKey: string): InfluenceTargetIn | null {
  if (!targeted(actionKey)) return null;
  return {
    character_id: form.who.startsWith("c:") ? form.who.slice(2) : null,
    entry: form.who === "entry" ? form.entry : null,
    type: form.type || null,
    activity: form.activity,
  };
}

/** What an Attack, Defend, Boost or Block is aimed at, in the entry form. */
export function TargetFields({
  choices,
  actionKey,
  type,
  form,
  onChange,
}: {
  choices: InfluenceChoicesOut;
  actionKey: string;
  type: InfluenceType;
  form: TargetForm;
  onChange: (change: Partial<TargetForm>) => void;
}) {
  if (!targeted(actionKey)) return null;
  const characters = choices.characters.filter((c) => c.in_troupe || `c:${c.id}` === form.who);
  const other: InfluenceType = type === "elite" ? "underworld" : "elite";
  if (actionKey === "block")
    return (
      <>
        <Field label="Blocked activity" hint="Each action adds 1 to its cost.">
          <Input value={form.activity} onChange={(e) => onChange({ activity: e.target.value })} placeholder="Acquiring firearms" />
        </Field>
        <Field label="Influence blocked">
          <Select value={form.type} onChange={(e) => onChange({ type: e.target.value as TargetForm["type"] })}>
            <option value="">{TYPE_NAMES[type]}</option>
            <option value={other}>{TYPE_NAMES[other]}</option>
          </Select>
        </Field>
      </>
    );
  const label = { attack: "Attacking", boost: "Boosting", defend: "Defending" }[actionKey] ?? "Target";
  return (
    <>
      <Field label={label}>
        <Select value={form.who} onChange={(e) => onChange({ who: e.target.value })}>
          <option value="">{actionKey === "defend" ? "Their own influence" : "Choose…"}</option>
          {characters.map((c) => (
            <option key={c.id} value={`c:${c.id}`}>
              {c.name}
              {c.kind === "npc" ? " (NPC)" : ""}
            </option>
          ))}
          {actionKey === "attack" && <option value="entry">Whoever took a log entry…</option>}
        </Select>
      </Field>
      {form.who === "entry" && (
        <Field label="Entry" hint="Its short id, such as UW268.">
          <Input value={form.entry} onChange={(e) => onChange({ entry: e.target.value })} />
        </Field>
      )}
      {actionKey === "attack" && form.who !== "entry" && (
        <Field label="Influence attacked" hint="Across types costs 3 actions a level, not 2.">
          <Select value={form.type} onChange={(e) => onChange({ type: e.target.value as TargetForm["type"] })}>
            <option value="">{TYPE_NAMES[type]}</option>
            <option value={other}>{TYPE_NAMES[other]}</option>
          </Select>
        </Field>
      )}
    </>
  );
}

/** Resolve an Attack, Boost, Block or location action: check what it would record, then record it. */
export function ResolveButton({ entry }: { entry: InfluenceEntryOut }) {
  const [open, setOpen] = useState(false);
  if (!entry.resolves || entry.effect || entry.needs_details) return null;
  return (
    <>
      <Button variant="ghost" className="px-2 py-0" onClick={() => setOpen(true)}>
        Resolve
      </Button>
      <Dialog title={`Resolve ${entry.short_id}`} open={open} onClose={() => setOpen(false)}>
        <ResolveForm entry={entry} onDone={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

function ResolveForm({ entry, onDone }: { entry: InfluenceEntryOut; onDone: () => void }) {
  const dates = useDates();
  const [levels, setLevels] = useState<number | null>(null);
  const [activity, setActivity] = useState<string | null>(null);
  const block = entry.resolves === "block";
  const query = { levels: levels ?? undefined };
  const plan = useQuery({
    queryKey: ["influence-plan", entry.id, query],
    queryFn: () => unwrap(api.GET("/api/influence-entries/{entry_id}/resolution", { params: { path: { entry_id: entry.id }, query } })),
    // Keep the last plan showing while a new number of levels is worked out.
    placeholderData: (previous) => previous,
  });
  const resolve = useAction(async () => {
    await unwrap(
      api.POST("/api/influence-entries/{entry_id}/resolution", {
        params: { path: { entry_id: entry.id } },
        body: { levels, activity: block ? (activity ?? plan.data?.activity) : null },
      }),
    );
    onDone();
  });

  if (plan.isPending) return <Loading />;
  if (plan.error) return <ErrorText error={plan.error} />;
  const p = plan.data;
  const type = TYPE_NAMES[p.type];
  return (
    <form
      aria-label={`Resolve ${entry.short_id}`}
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        resolve.mutate(undefined);
      }}
    >
      {block ? (
        <>
          <p>
            A {type} block, from {dates.dateTime(p.starts_at)} to {dates.dateTime(p.ends_at)}.
          </p>
          <Field label="Blocked activity">
            <Input value={activity ?? p.activity} onChange={(e) => setActivity(e.target.value)} />
          </Field>
        </>
      ) : (
        <p>
          {p.kind === "attack" ? `An attack on ${p.name}'s ${type}` : `A boost to ${p.name}'s ${type}`}, at {p.rating} now.
        </p>
      )}
      <Field label={block ? "Strength" : "Levels"} hint={costText(p, entry.short_id)}>
        <Input type="number" min={0} max={10} value={levels ?? p.levels} onChange={(e) => setLevels(Number(e.target.value))} />
      </Field>
      {p.kind === "attack" && (
        <p aria-label="Defends">
          {p.defended
            ? `${p.name}'s Defends (${p.defends.join(", ")}) take ${p.defended} ${p.defended === 1 ? "level" : "levels"} off.`
            : `No Defends of ${p.name}'s count against it.`}{" "}
          {p.name} loses {p.result} {p.result === 1 ? "level" : "levels"} and as many actions, until {dates.date(p.ends_at)}, or 2 more games if
          that is later.
        </p>
      )}
      {p.kind === "boost" && (
        <p>
          {p.name} is at {p.rating + p.result} until {dates.date(p.ends_at)}, with {p.result} more {p.result === 1 ? "action" : "actions"} this
          month.
        </p>
      )}
      {p.notes.map((n) => (
        <p key={n} className="text-gold">
          {n}
        </p>
      ))}
      <ErrorText error={resolve.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={resolve.isPending || (!block && (levels ?? p.levels) < 1)}>
          {p.kind === "attack" ? "Record the attack" : p.kind === "boost" ? "Record the boost" : "Record the block"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The troupe's effects and blocks holding now, and recording a block with no entry behind it. */
export function EffectsCard({ troupeId }: { troupeId: string }) {
  const dates = useDates();
  const [adding, setAdding] = useState(false);
  const effects = useQuery({
    queryKey: ["influence-effects", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/influence-effects", { params: { path: { troupe_id: troupeId } } })),
  });
  const remove = useAction(async (effect: InfluenceEffectOut) => {
    const removed = await unwrap(api.DELETE("/api/influence-effects/{effect_id}", { params: { path: { effect_id: effect.id } } }));
    if (removed.note) window.alert(removed.note);
  });

  return (
    <Card
      title="Effects and blocks"
      actions={
        !adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Record a block
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">Attacks, Boosts and Blocks holding now. They end by themselves.</p>
      {adding && <BlockForm troupeId={troupeId} onDone={() => setAdding(false)} />}
      {effects.isPending ? (
        <Loading />
      ) : effects.error ? (
        <ErrorText error={effects.error} />
      ) : effects.data.length === 0 ? (
        <Empty>Nothing holding now.</Empty>
      ) : (
        <ul className="flex flex-col gap-2 text-sm" aria-label="Effects and blocks">
          {effects.data.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {e.entry_short_id && <strong className="text-gold">{e.entry_short_id}</strong>}
              <span>
                {e.kind === "block" ? e.text : `${e.name}: ${e.text}`}
                {e.defended > 0 && ` (${e.defended} defended)`}
              </span>
              <span className="text-mist">{e.upcoming ? `from ${dates.dateTime(e.starts_at)}` : lastsText(e, dates)}</span>
              {e.kind === "block" && <Badge>Strength {e.levels}</Badge>}
              <Button
                variant="ghost"
                className="ml-auto px-2 py-0"
                onClick={() => {
                  if (window.confirm(`Take back ${e.text}?`)) remove.mutate(e);
                }}
              >
                Take back
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={remove.error} />
    </Card>
  );
}

function BlockForm({ troupeId, onDone }: { troupeId: string; onDone: () => void }) {
  const dates = useDates();
  const [form, setForm] = useState({ type: "underworld" as InfluenceType, activity: "", strength: 1, starts_at: dates.toInput(new Date()), ends_at: "" });
  const set = (change: Partial<typeof form>) => setForm({ ...form, ...change });
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/influence-blocks", {
        params: { path: { troupe_id: troupeId } },
        body: {
          type: form.type,
          activity: form.activity,
          strength: form.strength,
          starts_at: dates.fromInput(form.starts_at).toISOString(),
          ends_at: form.ends_at ? dates.fromInput(form.ends_at).toISOString() : null,
        },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Record a block"
      className="mb-4 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Blocked activity">
          <Input value={form.activity} onChange={(e) => set({ activity: e.target.value })} placeholder="Acquiring firearms" />
        </Field>
        <Field label="Influence blocked">
          <Select value={form.type} onChange={(e) => set({ type: e.target.value as InfluenceType })}>
            <option value="elite">Elite</option>
            <option value="underworld">Underworld</option>
          </Select>
        </Field>
        <Field label="Strength">
          <Input type="number" min={1} value={form.strength} onChange={(e) => set({ strength: Number(e.target.value) })} />
        </Field>
        <Field label={`From (${dates.zoneName()})`}>
          <Input type="datetime-local" value={form.starts_at} onChange={(e) => set({ starts_at: e.target.value })} />
        </Field>
        <Field label="Until" hint="Left empty, to the end of the month.">
          <Input type="datetime-local" value={form.ends_at} onChange={(e) => set({ ends_at: e.target.value })} />
        </Field>
      </div>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending || !form.activity.trim()}>
          Record it
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
