import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { RadioList } from "../../components/RadioList";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { Button, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useCatalogue } from "../../catalogue";
import { SectionLabel } from "../../components/Headings";
import { SETTINGS } from "./settingsIndex";

type Kind = "none" | "date" | "games";
type Excluded = { category: string; name: string };
type Draft = { kind: Kind; days: number; games: number; excluded: Excluded[] };

const KINDS: { value: Kind; label: string; meaning: string }[] = [
  {
    value: "none",
    label: "No free changes",
    meaning: "Locked on acceptance: once the troupe accepts a character, only its normal rules for lowering and removing traits apply.",
  },
  {
    value: "date",
    label: "By date",
    meaning: "Free changes for a number of days from the day the troupe accepts the character.",
  },
  {
    value: "games",
    label: "By games played",
    meaning: "Free changes until the character has attended a number of the troupe's games, counted from check-in. A missed game never counts.",
  },
];

/**
 * House rule: free changes for new characters (horatio.free_changes). For a while after
 * the troupe accepts a character, its player can lower or remove traits for their full
 * XP, as during creation, each change reviewed on the Approvals tab. Traits the troupe
 * lists are never refunded so.
 */
export function FreeChangesSettings({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const setting = useQuery({
    queryKey: ["free-changes", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/free-changes", path)),
  });
  if (setting.isPending) return <Loading />;
  if (setting.error) return <ErrorText error={setting.error} />;
  const now: Draft = {
    kind: setting.data.kind,
    days: setting.data.days,
    games: setting.data.games,
    excluded: setting.data.excluded,
  };

  return (
    <SettingCard
      setting={SETTINGS.freeChangeRules}
      readOnly={!canEdit}
    >
      {canEdit ? (
        <FreeChangesForm troupeId={troupeId} saved={now} />
      ) : (
        <div className="flex flex-col gap-1 text-sm">
          <p>{setting.data.text}.</p>
          {now.kind !== "none" && (
            <p className="text-mist">
              {now.excluded.length ? `Never refunded: ${now.excluded.map((e) => e.name).join(", ")}.` : "Every trait can be refunded."}
            </p>
          )}
        </div>
      )}
    </SettingCard>
  );
}

function FreeChangesForm({ troupeId, saved }: { troupeId: string; saved: Draft }) {
  const form = useSettingForm(saved, (body) => unwrap(api.PUT("/api/troupes/{troupe_id}/free-changes", { params: { path: { troupe_id: troupeId } }, body })));
  const draft = form.value;
  const onChange = (next: Draft) => form.set(next);
  return (
    <SettingForm form={form}>
      <RadioList
        label="Free changes"
        hideLabel
        value={draft.kind}
        options={KINDS.map((k) => ({ value: k.value, label: k.label, hint: k.meaning }))}
        onChange={(kind) => onChange({ ...draft, kind })}
      />
      {draft.kind === "date" && (
        <Field label="Days from acceptance">
          <Input type="number" min={1} max={365} required value={draft.days} onChange={(e) => onChange({ ...draft, days: Number(e.target.value) })} className="w-24" />
        </Field>
      )}
      {draft.kind === "games" && (
        <Field label="Games attended">
          <Input type="number" min={1} max={50} required value={draft.games} onChange={(e) => onChange({ ...draft, games: Number(e.target.value) })} className="w-24" />
        </Field>
      )}
      {draft.kind !== "none" && <NeverRefunded draft={draft} onChange={onChange} />}
    </SettingForm>
  );
}

/** The traits that keep the normal rules while free changes are open, picked from the rule set. */
function NeverRefunded({ draft, onChange }: { draft: Draft; onChange: (draft: Draft) => void }) {
  // The rule set as written, to pick the traits never refunded from.
  const catalogue = useCatalogue("vampire", null);
  const [category, setCategory] = useState("merits");
  const [name, setName] = useState("");
  const categories = (catalogue.data?.categories ?? []).filter((c) => c.rated && !c.derived);
  const names = (catalogue.data?.traits ?? []).filter((t) => t.category === category).map((t) => t.name);
  const found = names.find((n) => n.toLowerCase() === name.trim().toLowerCase());
  const has = (e: Excluded) => draft.excluded.some((x) => x.category === e.category && x.name === e.name);
  const add = () => {
    if (!found || has({ category, name: found })) return;
    onChange({ ...draft, excluded: [...draft.excluded, { category, name: found }] });
    setName("");
  };

  return (
    <div className="flex flex-col gap-2">
      <SectionLabel>Never refunded</SectionLabel>
      <p className="text-xs text-mist">Traits that follow the normal rules even while free changes are open, such as Efficient Learner or Arcane.</p>
      {draft.excluded.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Never refunded">
          {draft.excluded.map((e) => (
            <li key={`${e.category}/${e.name}`} className="flex items-center gap-1 rounded-md border border-ash px-2 py-1 text-sm">
              {e.name}
              <button
                type="button"
                className="min-h-6 px-1 text-mist hover:text-parchment"
                aria-label={`Refund ${e.name} again`}
                onClick={() => onChange({ ...draft, excluded: draft.excluded.filter((x) => !(x.category === e.category && x.name === e.name)) })}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Category">
          <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-40">
            {categories.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Trait">
          <Input
            list="free-changes-traits"
            value={name}
            placeholder="Search…"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            className="w-56"
          />
        </Field>
        <datalist id="free-changes-traits">
          {names.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
        <Button type="button" variant="secondary" disabled={!found} onClick={add}>
          Add
        </Button>
      </div>
      <ErrorText error={catalogue.error} />
    </div>
  );
}
