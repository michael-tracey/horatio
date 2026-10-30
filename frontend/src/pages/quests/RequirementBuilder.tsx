import { useState } from "react";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { emptyDraft, OPTION_KINDS, optionsFrom, TRAIT_KINDS, type Option, type OptionDraft, type OptionKind } from "./quests";

/**
 * A requirement's alternatives, any one of which meets it ("Medicine 3 or Science
 * (Biology)"): each a trait, an aspect, something to expend, or words. Used for a
 * quest's requirements, and made to be used for anything else with requirements.
 */
export function RequirementBuilder({
  onAdd,
  pending,
  error,
  submitLabel = "Add requirement",
}: {
  onAdd: (options: Option[]) => Promise<unknown>;
  pending: boolean;
  error: unknown;
  submitLabel?: string;
}) {
  const [drafts, setDrafts] = useState<OptionDraft[]>([emptyDraft()]);
  const [problem, setProblem] = useState<string | null>(null);
  const set = (i: number, change: Partial<OptionDraft>) => setDrafts(drafts.map((d, j) => (j === i ? { ...d, ...change } : d)));

  return (
    <form
      aria-label="New requirement"
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const options = optionsFrom(drafts);
        if (typeof options === "string") {
          setProblem(options);
          return;
        }
        setProblem(null);
        await onAdd(options);
        setDrafts([emptyDraft()]);
      }}
    >
      {drafts.map((d, i) => (
        <fieldset key={i} aria-label={`Alternative ${i + 1}`} className="flex flex-col gap-2 rounded-md border border-ash p-3">
          <legend className="px-1 text-xs text-mist">{i === 0 ? "Requirement" : "Or"}</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="Kind">
              <Select value={d.kind} onChange={(e) => set(i, { ...emptyDraft(e.target.value as OptionKind) })}>
                {OPTION_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </Select>
            </Field>
            <OptionFields draft={d} onChange={(change) => set(i, change)} />
          </div>
          {drafts.length > 1 && (
            <Button type="button" variant="ghost" className="self-start" onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}>
              Remove this alternative
            </Button>
          )}
        </fieldset>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={() => setDrafts([...drafts, emptyDraft()])}>
          Add an alternative
        </Button>
        <Button type="submit" disabled={pending}>
          {submitLabel}
        </Button>
      </div>
      {problem && <ErrorText error={problem} />}
      <ErrorText error={error} />
    </form>
  );
}

function OptionFields({ draft: d, onChange }: { draft: OptionDraft; onChange: (change: Partial<OptionDraft>) => void }) {
  const text = (label: string, key: keyof OptionDraft, hint?: string) => (
    <Field label={label} hint={hint}>
      <Input value={d[key]} onChange={(e) => onChange({ [key]: e.target.value })} />
    </Field>
  );
  const number = (label: string, key: keyof OptionDraft, min: number) => (
    <Field label={label}>
      <Input type="number" min={min} max={20} value={d[key]} onChange={(e) => onChange({ [key]: e.target.value })} />
    </Field>
  );
  switch (d.kind) {
    case "trait":
      return (
        <>
          <Field label="Trait type">
            <Select value={d.category} onChange={(e) => onChange({ category: e.target.value })}>
              {TRAIT_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Field>
          {text("Name", "name", d.category === "power" ? "The power's name, such as Earth Meld." : undefined)}
          {number("Rating", "rating", 0)}
          {text("Specialisation", "specialization", "Optional: Lore: Abyss is Lore with Abyss.")}
        </>
      );
    case "aspect":
      return (
        <>
          <Field label="Aspect">
            <Select value={d.aspect} onChange={(e) => onChange({ aspect: e.target.value })}>
              <option value="clan">Clan</option>
              <option value="bloodline">Bloodline</option>
              <option value="sect">Sect</option>
            </Select>
          </Field>
          {text("Name", "name")}
        </>
      );
    case "influence":
      return (
        <>
          <Field label="Influence">
            <Select value={d.type} onChange={(e) => onChange({ type: e.target.value })}>
              <option value="elite">Elite</option>
              <option value="underworld">Underworld</option>
            </Select>
          </Field>
          {number("Level", "level", 1)}
          {text("Area", "area", "Optional: its specialisation, such as High Society.")}
        </>
      );
    case "background":
      return (
        <>
          {text("Background", "name")}
          {number("Dots", "dots", 1)}
        </>
      );
    case "status":
      return text("Status", "name", "Optional: a fleeting status by name; any one if left empty.");
    case "pool":
      return (
        <>
          <Field label="Pool">
            <Select value={d.pool} onChange={(e) => onChange({ pool: e.target.value })}>
              <option value="willpower">Willpower</option>
              <option value="blood">Blood</option>
            </Select>
          </Field>
          {number("Amount", "amount", 1)}
        </>
      );
    case "action":
      return text("Action kind", "action_kind");
    case "item":
      return text("Item", "item");
    case "text":
      return text("Text", "text", "What Horatio can't check, such as Access to Miles' journal.");
  }
}
