import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, GiveOut, SheetTraitOut, TraitOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Notice, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { detailNeed } from "./fields";

const SHOWN = 40;

/**
 * Staff give a player's character a trait, or raise one, by exception: free,
 * despite the rules, or both, always with a reason. Check says what it would
 * cost and which rules it breaks; giving it despite them needs a tick. Nothing
 * waits on approval, and the player is told.
 */
export function GivePanel({
  character,
  catalogue,
  categories,
  held,
  onClose,
}: {
  character: CharacterOut;
  catalogue: CatalogueOut;
  /** Category keys this part of the sheet gives in. */
  categories: string[];
  held: SheetTraitOut[];
  onClose: () => void;
}) {
  const [category, setCategory] = useState(categories[0] ?? "");
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const [free, setFree] = useState(false);
  const [despite, setDespite] = useState(false);
  const [reason, setReason] = useState("");
  const [trial, setTrial] = useState<GiveOut | null>(null);
  const cat = catalogue.categories.find((c) => c.key === category);
  const all = useMemo(() => catalogue.traits.filter((t) => t.category === category), [catalogue, category]);
  const q = query.trim().toLowerCase();
  const matching = all.filter((t) => !q || t.name.toLowerCase().includes(q));
  const trait = all.find((t) => t.name === name);
  const fixed = trait?.fixed_rating ?? null;
  const now = held.find((h) => h.category === category && h.name === name && h.detail === detail)?.rating ?? 0;
  const body = { category, name, detail, rating: fixed ?? rating, free, despite, reason: reason.trim(), trial: false };
  const changed = () => setTrial(null);

  const check = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/characters/{character_id}/give", { params: { path: { character_id: character.id } }, body: { ...body, despite: true, trial: true } })),
    onSuccess: setTrial,
  });
  const give = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/give", { params: { path: { character_id: character.id } }, body }));
    onClose();
  });
  const choose = (t: TraitOut) => {
    setName(t.name);
    setDetail("");
    setRating((held.find((h) => h.category === category && h.name === t.name)?.rating ?? 0) + 1);
    changed();
  };
  const breaks = trial?.breaks ?? [];
  // Checked as if despite the rules: anything still refused, giving cannot set aside.
  const refusedOtherwise = trial?.refused ?? null;

  return (
    <div className="mb-4 flex flex-col gap-3 rounded-md border border-gold/40 bg-night/40 p-3">
      <p className="text-xs text-mist">
        Give {character.name} a trait, or raise one, by exception: free, despite the rules, or both. It needs no approval; the player is told.
      </p>
      <div className="flex flex-wrap gap-2">
        {categories.length > 1 && (
          <Select
            aria-label="Category to give in"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setName("");
              changed();
            }}
            className="w-auto"
          >
            {categories.map((key) => (
              <option key={key} value={key}>
                {catalogue.categories.find((c) => c.key === key)?.name ?? key}
              </option>
            ))}
          </Select>
        )}
        <Input
          aria-label={`Search ${cat?.name ?? ""} to give`}
          placeholder={`Search ${matching.length} ${cat?.name.toLowerCase() ?? ""}…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-40 flex-1"
        />
      </div>
      <ul className="flex max-h-60 flex-col overflow-y-auto">
        {matching.slice(0, SHOWN).map((t) => {
          const has = held.find((h) => h.category === category && h.name === t.name);
          return (
            <li key={t.name}>
              <button
                type="button"
                onClick={() => choose(t)}
                className={`flex w-full justify-between rounded px-2 py-1.5 text-left text-sm ${t.name === name ? "bg-ash/60" : "hover:bg-ash/40"}`}
              >
                <span>
                  {t.name}
                  {t.fixed_rating ? <span className="text-gold"> ({t.fixed_rating})</span> : null}
                </span>
                {has && <span className="text-xs text-mist">has {has.rating}</span>}
              </button>
            </li>
          );
        })}
        {matching.length === 0 && <li className="px-2 text-sm text-mist">Nothing matches.</li>}
        {matching.length > SHOWN && <li className="px-2 text-xs text-mist">Search to see all {matching.length}.</li>}
      </ul>
      {trait && (
        <form
          aria-label={`Give ${trait.name}`}
          className="flex flex-col gap-3 border-t border-ash pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            give.mutate(undefined);
          }}
        >
          <p className="text-sm text-parchment">
            {trait.name}
            {now > 0 && <span className="text-mist"> (has {now})</span>}
          </p>
          {trait.choices ? (
            <Field label="Which?">
              <Select
                required
                value={detail}
                onChange={(e) => {
                  setDetail(e.target.value);
                  changed();
                }}
              >
                <option value="">Choose…</option>
                {trait.choices.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
          ) : (
            <Field label={detailNeed(trait)?.label ?? "Detail"} hint={detailNeed(trait)?.hint ?? "Optional: a specialisation, subject, or name."}>
              <Input
                required={!!detailNeed(trait)}
                value={detail}
                onChange={(e) => {
                  setDetail(e.target.value);
                  changed();
                }}
              />
            </Field>
          )}
          {cat?.rated && fixed === null && (
            <Field label="Rating">
              <Input
                type="number"
                min={now + 1}
                max={cat.max_rating ?? undefined}
                value={rating}
                onChange={(e) => {
                  setRating(Number(e.target.value));
                  changed();
                }}
              />
            </Field>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={free}
              onChange={(e) => {
                setFree(e.target.checked);
                changed();
              }}
            />
            Free: at no XP cost
          </label>
          <Field label="Reason" hint="Kept with the trait, and in the XP history.">
            <Input required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          {trial && (
            <div className="flex flex-col gap-2 text-sm">
              <p>{free ? "Free." : trial.cost > 0 ? `Costs ${trial.cost} XP.` : trial.cost < 0 ? `Gives ${-trial.cost} XP back.` : "Costs nothing."}</p>
              {breaks.length > 0 && (
                <div className="rounded-md border border-blood/60 bg-blood/10 p-2">
                  <p className="text-xs text-mist">It breaks:</p>
                  <ul className="list-disc pl-5 text-xs text-blood-bright">
                    {breaks.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                  <label className="mt-2 flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={despite} onChange={(e) => setDespite(e.target.checked)} />
                    Give it despite these rules
                  </label>
                </div>
              )}
              {refusedOtherwise && <p className="text-xs text-blood-bright">{refusedOtherwise}</p>}
              {!breaks.length && !refusedOtherwise && <Notice>It breaks no rules.</Notice>}
            </div>
          )}
          <ErrorText error={check.error ?? give.error} />
          <div className="flex gap-2">
            <Button type="button" variant="secondary" disabled={check.isPending || !reason.trim()} onClick={() => check.mutate()}>
              Check
            </Button>
            <Button type="submit" disabled={!trial || give.isPending || !!refusedOtherwise || (breaks.length > 0 && !despite)}>
              Give
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
