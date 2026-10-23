import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetTraitOut, TraitOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Notice, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { AskStaff } from "./AskStaff";
import type { CartLine, Exception } from "./cart";
import { foundElsewhere, shownChips, useBarred, useChoices } from "./choices";
import { QuickPicks } from "./creation/DotGrid";
import { FIELD_PLACEHOLDER } from "./fields";
import { applyFilter, byKind, countOf, filterChoices, quickPicks } from "./traitFilter";

const SHOWN = 40;

/** A new trait for the cart. */
export type NewTrait = { category: string; name: string; detail: string; rating: number; teacher: string; fixed: boolean; exception?: Exception };

/**
 * Add a trait to one part of the sheet: pick a category from its chips, then from
 * a searchable list of what the character can take there (or everything), see
 * what it costs, and put it in the cart. Traits the rules would refuse are greyed
 * out with the reason. What the character can take counts the cart.
 */
export function AddTraitPanel({
  character,
  catalogue,
  categories,
  held,
  lines,
  initial,
  onAdd,
  onClose,
}: {
  character: CharacterOut;
  catalogue: CatalogueOut;
  /** Category keys this part of the sheet adds to. */
  categories: string[];
  held: SheetTraitOut[];
  /** The cart, which the lists are judged with. */
  lines: CartLine[];
  /** The category to open on; the first if not given. */
  initial?: string;
  onAdd: (trait: NewTrait) => void;
  onClose: () => void;
}) {
  const [category, setCategory] = useState(initial ?? categories[0] ?? "");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("can");
  const [name, setName] = useState("");
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const [quote, setQuote] = useState<number | null>(null);
  const [teacher, setTeacher] = useState("");
  // A trait the rules refuse, asked of staff as an exception.
  const [asking, setAsking] = useState<TraitOut | null>(null);
  const cat = catalogue.categories.find((c) => c.key === category);
  const choices = useChoices(character.id, catalogue, categories, held, lines);
  const current = choices.find((c) => c.key === category);
  const unavailable = current?.refused ?? {};
  const all = current?.traits ?? [];
  const filterable = byKind(all);
  const mine = new Set(held.filter((h) => h.category === category && !h.detail).map((h) => h.name));
  const q = query.trim().toLowerCase();
  const barred = useBarred(character.id, current);
  const shown = applyFilter(all, filter, barred).filter((t) => !mine.has(t.name));
  const matching = shown.filter((t) => !q || t.name.toLowerCase().includes(q));
  // What "can take" leaves out, a tap away: greyed with the reason under Everything.
  const leftOut =
    filter === "can" && current?.ready ? all.filter((t) => !mine.has(t.name) && (!q || t.name.toLowerCase().includes(q))).length - matching.length : 0;
  // Nothing here: perhaps it lives in another category.
  const elsewhere = matching.length === 0 ? foundElsewhere(choices, category, query, held).slice(0, 5) : [];
  const switchTo = (key: string, can = true) => {
    setCategory(key);
    setName("");
    setFilter(can ? "can" : "all");
  };
  const trait = all.find((t) => t.name === name);
  const fixed = trait?.fixed_rating ?? null;
  // Skills bought once per field, such as Performance: Singing (MET: VTM p. 92).
  const needsField = !!trait?.needs_field;
  // After acceptance, discipline dots wait on the home troupe, who will want to know the teacher.
  const asksTeacher = category === "disciplines" && character.home_troupe_id !== null;
  const body = { category, name, detail, rating: cat?.rated ? (fixed ?? rating) : null, teacher: asksTeacher ? teacher : "" };

  const choose = (t: TraitOut) => {
    setAsking(null);
    setName(t.name);
    setDetail("");
    setRating(1);
    setQuote(null);
  };
  const price = useAction(async () => {
    const result = await unwrap(api.POST("/api/characters/{character_id}/quote", { params: { path: { character_id: character.id } }, body }));
    setQuote(result.cost);
  });
  const add = () => {
    onAdd({ category, name, detail, rating: body.rating ?? 1, teacher: body.teacher, fixed: fixed !== null });
    onClose();
  };

  return (
    <div className="mb-4 flex flex-col gap-3 rounded-md border border-ash bg-night/40 p-3">
      {categories.length > 1 && (
        <CategoryChips
          label="Categories"
          tabs={shownChips(choices, category).map((c) => ({ key: c.key, label: c.name, count: c.ready ? c.canTake.length : undefined }))}
          value={category}
          onChange={(key) => switchTo(key)}
        />
      )}
      <div className="flex flex-wrap gap-2">
        {filterable && <QuickPicks picks={quickPicks(all, held)} filter={filter} onFilter={setFilter} title={cat?.name ?? ""} />}
        <Select aria-label="Show" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-auto">
          {filterChoices(all, true).map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </Select>
        <Input
          aria-label={`Search ${cat?.name ?? ""}`}
          placeholder={`Search ${countOf(shown.length, cat?.name ?? "")}${filter === "can" ? " you can take" : ""}…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-40 flex-1"
        />
      </div>
      <ul className="flex max-h-72 flex-col overflow-y-auto">
        {matching.slice(0, SHOWN).map((t) => (
          <TraitChoice
            key={t.name}
            trait={t}
            chosen={t.name === name}
            refused={unavailable[t.name]}
            onChoose={() => choose(t)}
            onAsk={
              character.home_troupe_id
                ? () => {
                    setName("");
                    setAsking(t);
                  }
                : undefined
            }
          />
        ))}
        {elsewhere.map((found) => (
          <li key={`${found.category.key}/${found.trait.name}`}>
            <button
              type="button"
              onClick={() => switchTo(found.category.key, found.canTake)}
              className="w-full rounded px-2 py-1.5 text-left text-sm text-mist hover:bg-ash/40 hover:text-parchment"
            >
              Found in {found.category.name}: <span className="text-parchment">{found.trait.name}</span>
            </button>
          </li>
        ))}
        {matching.length === 0 && elsewhere.length === 0 && leftOut === 0 && <li className="px-2 text-sm text-mist">Nothing matches.</li>}
        {matching.length > SHOWN && <li className="px-2 text-xs text-mist">Search to see all {matching.length}.</li>}
        {leftOut > 0 && (
          <li className="px-2 py-1.5 text-xs text-mist">
            {matching.length > 0 ? `${leftOut} more you can't take: ` : `None you can take. ${leftOut} you can't: `}
            <button type="button" onClick={() => setFilter("all")} className="text-gold underline hover:text-parchment">
              show
            </button>
          </li>
        )}
      </ul>
      {asking && (
        <AskStaff
          key={asking.name}
          name={asking.name}
          refusal={unavailable[asking.name] ?? ""}
          trait={asking}
          rated={!!cat?.rated}
          maxRating={cat?.max_rating}
          onCancel={() => setAsking(null)}
          onAsk={(exception, chosen) => {
            onAdd({ category, name: asking.name, ...chosen, teacher: "", fixed: asking.fixed_rating != null, exception });
            onClose();
          }}
        />
      )}
      {trait && (
        <form
          className="flex flex-col gap-3 border-t border-ash pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            add();
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
            <Field label={needsField ? "Field" : "Detail"} hint={needsField ? "Bought once per field." : "Optional: a specialisation, subject, or name."}>
              <Input required={needsField} placeholder={needsField ? FIELD_PLACEHOLDER : undefined} value={detail} onChange={(e) => setDetail(e.target.value)} />
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
          <ErrorText error={price.error} />
          <div className="flex gap-2">
            {cat?.rated && (
              <Button type="button" variant="secondary" disabled={price.isPending} onClick={() => price.mutate(undefined)}>
                Price it
              </Button>
            )}
            <Button type="submit">Add to cart</Button>
          </div>
        </form>
      )}
    </div>
  );
}

/**
 * One trait in the list: chosen, or greyed with why the rules refuse it, and then
 * (given `onAsk`) a way to ask staff for it as an exception.
 */
function TraitChoice({
  trait,
  chosen,
  refused,
  onChoose,
  onAsk,
}: {
  trait: TraitOut;
  chosen: boolean;
  refused?: string;
  onChoose: () => void;
  onAsk?: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        disabled={!!refused}
        onClick={onChoose}
        className={`flex w-full flex-col rounded px-2 py-1.5 text-left text-sm ${chosen ? "bg-ash/60" : "hover:bg-ash/40"} ${refused ? "opacity-50" : ""}`}
      >
        <span>
          {trait.name}
          {trait.fixed_rating ? <span className="text-gold"> ({trait.fixed_rating})</span> : null}
          {trait.requirement && <span className="ml-2 text-xs text-mist">{trait.requirement}</span>}
        </span>
        {refused && <span className="text-xs text-blood-bright">{refused}</span>}
      </button>
      {refused && onAsk && (
        <button type="button" className="ml-2 text-xs text-gold underline" onClick={onAsk}>
          Ask staff
        </button>
      )}
    </li>
  );
}

/**
 * The part's categories as chips, each with how many the character can take
 * there. Drawn like SubTabs, and taking a label and tabs as it does, but
 * choosing in place rather than following a link.
 */
function CategoryChips({
  label,
  tabs,
  value,
  onChange,
}: {
  label: string;
  tabs: { key: string; label: string; count?: number }[];
  value: string;
  onChange: (key: string) => void;
}) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          aria-pressed={t.key === value}
          onClick={() => onChange(t.key)}
          className={`rounded-full border px-3 py-1 text-sm whitespace-nowrap ${
            t.key === value ? "border-gold/60 bg-gold/10 text-parchment" : "border-ash text-mist hover:text-parchment"
          }`}
        >
          {t.label}
          {t.count ? (
            <>
              {" "}
              <span className="text-gold">{t.count}</span>
            </>
          ) : null}
        </button>
      ))}
    </nav>
  );
}
