import { useMemo, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetTraitOut, TraitOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Notice, Select } from "../../components/ui";
import { useAction, useUnavailable } from "../../hooks";
import { applyFilter, filterChoices } from "./traitFilter";

/** Skills bought once per field, such as Performance: Singing (MET: VTM p. 92). */
const NEEDS_FIELD = new Set(["Crafts", "Performance", "Science"]);
const SHOWN = 40;

/**
 * Add a trait to one part of the sheet: pick from a searchable list of the
 * part's categories, see what it costs, and buy it. Traits the rules would
 * refuse are greyed out with the reason.
 */
export function AddTraitPanel({
  character,
  catalogue,
  categories,
  held,
  onDone,
  onClose,
}: {
  character: CharacterOut;
  catalogue: CatalogueOut;
  /** Category keys this part of the sheet adds to. */
  categories: string[];
  held: SheetTraitOut[];
  onDone: (message: string) => void;
  onClose: () => void;
}) {
  const [category, setCategory] = useState(categories[0] ?? "");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("can");
  const [name, setName] = useState("");
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const [quote, setQuote] = useState<number | null>(null);
  const [teacher, setTeacher] = useState("");
  const cat = catalogue.categories.find((c) => c.key === category);
  const unavailable = useUnavailable(character.id, category).data ?? {};

  const all = useMemo(() => catalogue.traits.filter((t) => t.category === category), [catalogue, category]);
  const filterable = all.some((t) => t.kind || t.requirement);
  const mine = new Set(held.filter((h) => h.category === category && !h.detail).map((h) => h.name));
  const q = query.trim().toLowerCase();
  const matching = (filterable ? applyFilter(all, filter, unavailable) : all).filter(
    (t) => !mine.has(t.name) && (!q || t.name.toLowerCase().includes(q)),
  );
  const trait = all.find((t) => t.name === name);
  const fixed = trait?.fixed_rating ?? null;
  const needsField = category === "skills" && NEEDS_FIELD.has(name);
  // After acceptance, discipline dots wait on the home troupe, who will want to know the teacher.
  const asksTeacher = category === "disciplines" && character.home_troupe_id !== null;
  const body = { category, name, detail, rating: cat?.rated ? (fixed ?? rating) : null, teacher: asksTeacher ? teacher : "" };

  const choose = (t: TraitOut) => {
    setName(t.name);
    setDetail("");
    setRating(1);
    setQuote(null);
  };
  const price = useAction(async () => {
    const result = await unwrap(api.POST("/api/characters/{character_id}/quote", { params: { path: { character_id: character.id } }, body }));
    setQuote(result.cost);
  });
  const buy = useAction(async () => {
    const result = await unwrap(api.PUT("/api/characters/{character_id}/traits", { params: { path: { character_id: character.id } }, body }));
    onDone(result.cost ? `Added ${name} for ${result.cost} XP.` : `Added ${name}.`);
    onClose();
  });

  return (
    <div className="mb-4 flex flex-col gap-3 rounded-md border border-ash bg-night/40 p-3">
      <div className="flex flex-wrap gap-2">
        {categories.length > 1 && (
          <Select
            aria-label="Category"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setName("");
              setFilter("can");
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
        {filterable && (
          <Select aria-label="Show" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-auto">
            {filterChoices(all, true).map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </Select>
        )}
        <Input
          aria-label={`Search ${cat?.name ?? ""}`}
          placeholder={`Search ${matching.length} ${cat?.name.toLowerCase() ?? ""}…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-40 flex-1"
        />
      </div>
      <ul className="flex max-h-72 flex-col overflow-y-auto">
        {matching.slice(0, SHOWN).map((t) => {
          const barred = unavailable[t.name];
          return (
            <li key={t.name}>
              <button
                type="button"
                disabled={!!barred}
                onClick={() => choose(t)}
                className={`flex w-full flex-col rounded px-2 py-1.5 text-left text-sm ${t.name === name ? "bg-ash/60" : "hover:bg-ash/40"} ${barred ? "opacity-50" : ""}`}
              >
                <span>
                  {t.name}
                  {t.fixed_rating ? <span className="text-gold"> ({t.fixed_rating})</span> : null}
                  {t.requirement && <span className="ml-2 text-xs text-mist">{t.requirement}</span>}
                </span>
                {barred && <span className="text-xs text-blood-bright">{barred}</span>}
              </button>
            </li>
          );
        })}
        {matching.length === 0 && <li className="px-2 text-sm text-mist">Nothing matches.</li>}
        {matching.length > SHOWN && <li className="px-2 text-xs text-mist">Search to see all {matching.length}.</li>}
      </ul>
      {trait && (
        <form
          className="flex flex-col gap-3 border-t border-ash pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            buy.mutate(undefined);
          }}
        >
          <p className="text-sm text-parchment">{trait.name}</p>
          {trait.description && <p className="text-xs leading-relaxed text-mist">{trait.description}</p>}
          {trait.house_rule && <Notice>House rule: {trait.house_rule}</Notice>}
          {trait.choices ? (
            <Field label="Which?" hint={`${trait.name} gives one of these.`}>
              <Select required value={detail} onChange={(e) => setDetail(e.target.value)}>
                <option value="">Choose…</option>
                {trait.choices.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
          ) : (
            <Field label={needsField ? "Field" : "Detail"} hint={needsField ? "Bought once per field, such as Singing." : "Optional: a specialisation, subject, or name."}>
              <Input required={needsField} value={detail} onChange={(e) => setDetail(e.target.value)} />
            </Field>
          )}
          {cat?.rated && fixed === null && (
            <Field label="Rating">
              <Input
                type="number"
                min={1}
                max={cat.max_rating ?? undefined}
                value={rating}
                onChange={(e) => {
                  setRating(Number(e.target.value));
                  setQuote(null);
                }}
              />
            </Field>
          )}
          {asksTeacher && (
            <Field label="Teacher" hint="Out-of-clan powers need a teacher who has them in-clan.">
              <Input value={teacher} onChange={(e) => setTeacher(e.target.value)} />
            </Field>
          )}
          {quote !== null && <p className="text-sm">Costs {quote} XP.</p>}
          <ErrorText error={price.error ?? buy.error} />
          <div className="flex gap-2">
            {cat?.rated && (
              <Button type="button" variant="secondary" disabled={price.isPending} onClick={() => price.mutate(undefined)}>
                Price it
              </Button>
            )}
            <Button type="submit" disabled={buy.isPending}>
              {cat?.rated ? "Buy" : "Choose"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
