import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";

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
  const [draft, setDraft] = useState<Draft | null>(null);
  const save = useAction(async (body: Draft) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/free-changes", { ...path, body }));
    setDraft(null);
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
    <Card
      title="Free changes for new characters"
      actions={
        canEdit &&
        draft === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change free changes" onClick={() => setDraft(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        For a while after the troupe accepts a character, its player can lower or remove traits for their full XP back, as during creation. Each
        change still has to keep to the rules, and waits on the Approvals tab. Changing this applies to the characters whose free changes are open;
        turning it on gives them only to characters accepted from then on.
      </p>
      {draft === null ? (
        <div className="flex flex-col gap-1 text-sm">
          <p>{setting.data.text}.</p>
          {now.kind !== "none" && (
            <p className="text-mist">
              {now.excluded.length ? `Never refunded: ${now.excluded.map((e) => e.name).join(", ")}.` : "Every trait can be refunded."}
            </p>
          )}
        </div>
      ) : (
        <FreeChangesForm
          draft={draft}
          onChange={setDraft}
          onCancel={() => setDraft(null)}
          onSave={() => save.mutate(draft)}
          saving={save.isPending}
          error={save.error}
        />
      )}
    </Card>
  );
}

function FreeChangesForm({
  draft,
  onChange,
  onCancel,
  onSave,
  saving,
  error,
}: {
  draft: Draft;
  onChange: (draft: Draft) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
  error: unknown;
}) {
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", null],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: {} } })),
    staleTime: 5 * 60_000,
  });
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
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">Free changes</legend>
        {KINDS.map((k) => (
          <label key={k.value} className="flex items-start gap-2 text-sm">
            <input type="radio" name="free-changes" className="mt-1" checked={draft.kind === k.value} onChange={() => onChange({ ...draft, kind: k.value })} />
            <span>
              {k.label}
              <span className="block text-xs text-mist">{k.meaning}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {draft.kind === "date" && (
        <Field label="Days from acceptance">
          <Input type="number" min={1} max={365} required value={draft.days} onChange={(e) => onChange({ ...draft, days: Number(e.target.value) })} className="w-24" />
        </Field>
      )}
      {draft.kind === "games" && (
        <Field label="Games attended" hint="AIT uses 3.">
          <Input type="number" min={1} max={50} required value={draft.games} onChange={(e) => onChange({ ...draft, games: Number(e.target.value) })} className="w-24" />
        </Field>
      )}
      {draft.kind !== "none" && (
        <div className="flex flex-col gap-2">
          <h3 className="font-sans text-xs text-mist uppercase">Never refunded</h3>
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
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      <ErrorText error={error} />
    </form>
  );
}
