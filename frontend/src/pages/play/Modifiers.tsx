import { useState } from "react";
import type { PoolModifier, TestPool } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { describe } from "./pools";
import type { ModifierFields, useModifiers } from "./useModifiers";

const EMPTY: ModifierFields = { label: "", amount: 1, pools: "all", when: "" };

/** The pools a modifier can apply to: all, a group, or one of the pools the tab lists. */
function PoolPicker({ value, onChange, pools }: { value: string; onChange: (value: string) => void; pools: TestPool[] }) {
  return (
    <Select aria-label="Pools it applies to" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="all">Every pool</option>
      <option value="attack">Every attack</option>
      <option value="defense">Every defence</option>
      <option value="Physical">Physical pools</option>
      <option value="Social">Social pools</option>
      <option value="Mental">Mental pools</option>
      <optgroup label="One pool">
        {pools.map((p) => (
          <option key={p.key} value={`pool:${p.key}`}>
            {p.name}
          </option>
        ))}
      </optgroup>
    </Select>
  );
}

function ModifierForm({
  initial,
  pools,
  submit,
  busy,
  cancel,
}: {
  initial: ModifierFields;
  pools: TestPool[];
  submit: (fields: ModifierFields) => Promise<unknown>;
  busy: boolean;
  cancel?: () => void;
}) {
  const [form, setForm] = useState(initial);
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2 border-t border-ash pt-3"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await submit({ ...form, label: form.label.trim() });
          setForm(EMPTY);
        } catch {
          // The error shows under the form.
        }
      }}
    >
      <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-mist">
        {cancel ? "Label" : "Your own modifier"}
        <Input placeholder="Fame" value={form.label} required maxLength={80} onChange={(e) => setForm({ ...form, label: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-mist">
        Amount
        <Input type="number" min={-9} max={9} required value={form.amount} onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })} className="w-20" />
      </label>
      <label className="flex flex-col gap-1 text-xs text-mist">
        Applies to
        <PoolPicker value={form.pools} onChange={(pools) => setForm({ ...form, pools })} pools={pools} />
      </label>
      <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-mist">
        When (a note)
        <Input placeholder="against mortals" value={form.when} maxLength={80} onChange={(e) => setForm({ ...form, when: e.target.value })} />
      </label>
      <Button type="submit" variant="secondary" disabled={busy || form.amount === 0}>
        {cancel ? "Save" : "Add modifier"}
      </Button>
      {cancel && (
        <Button type="button" variant="secondary" onClick={cancel}>
          Cancel
        </Button>
      )}
    </form>
  );
}

function Row({ modifier, pools, modifiers }: { modifier: PoolModifier; pools: TestPool[]; modifiers: ReturnType<typeof useModifiers> }) {
  const [editing, setEditing] = useState(false);
  const { change, remove } = modifiers;
  return (
    <li className="py-2">
      <div className="flex items-center gap-3">
        <label className="flex min-h-10 min-w-0 flex-1 items-center gap-3">
          <input
            type="checkbox"
            className="h-5 w-5 shrink-0 accent-[var(--color-gold)]"
            checked={modifier.on}
            disabled={change.isPending}
            onChange={(e) => change.mutate({ id: modifier.id, on: e.target.checked })}
            aria-label={`${modifier.label} on`}
          />
          <span className="min-w-0">
            <span className={modifier.on ? "text-parchment" : "text-mist"}>{modifier.label}</span>
            <span className="block text-xs text-mist">{describe(modifier, pools)}</span>
          </span>
        </label>
        <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => setEditing(!editing)} aria-label={`Edit ${modifier.label}`}>
          edit
        </button>
        <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => remove.mutate(modifier.id)} aria-label={`Remove ${modifier.label}`}>
          remove
        </button>
      </div>
      {editing && (
        <ModifierForm
          initial={{ label: modifier.label, amount: modifier.amount, pools: modifier.pools, when: modifier.when }}
          pools={pools}
          busy={change.isPending}
          cancel={() => setEditing(false)}
          submit={async (fields) => {
            await change.mutateAsync({ id: modifier.id, ...fields });
            setEditing(false);
          }}
        />
      )}
    </li>
  );
}

/** "Your own": the player's own modifiers to the pools, on ones first, off ones listed below, ready to switch on. */
export function ModifiersPanel({ pools, modifiers }: { pools: TestPool[]; modifiers: ReturnType<typeof useModifiers> }) {
  const { add, change, remove } = modifiers;
  const on = modifiers.modifiers.filter((m) => m.on);
  const off = modifiers.modifiers.filter((m) => !m.on);
  return (
    <div className="border-t border-ash pt-2" role="group" aria-label="Your own">
      <h3 className="mb-1 text-xs tracking-wide text-mist uppercase">Your own</h3>
      {modifiers.modifiers.length === 0 && <p className="text-sm text-mist">Note a bonus or penalty from a merit, flaw, power, equipment or the scene. Switch it on while it counts.</p>}
      <ul className="divide-y divide-ash/60">
        {on.map((m) => (
          <Row key={m.id} modifier={m} pools={pools} modifiers={modifiers} />
        ))}
      </ul>
      {off.length > 0 && (
        <>
          <h4 className="mt-2 text-xs tracking-wide text-mist uppercase">Switched off</h4>
          <ul className="divide-y divide-ash/60">
            {off.map((m) => (
              <Row key={m.id} modifier={m} pools={pools} modifiers={modifiers} />
            ))}
          </ul>
        </>
      )}
      <ModifierForm initial={EMPTY} pools={pools} busy={add.isPending} submit={(fields) => add.mutateAsync(fields)} />
      <ErrorText error={add.error ?? change.error ?? remove.error} />
    </div>
  );
}
