import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetTraitOut, TraitOut } from "../../api/types";
import { HouseMark, HouseSummary } from "../../components/HouseMark";
import { Button, ErrorText, Field, Input, Notice, Select } from "../../components/ui";
import { AskStaff } from "./AskStaff";
import type { CartLine, Exception } from "./cart";
import { foundElsewhere, shownChips, useBarred, useChoices } from "./choices";
import { QuickPicks } from "./creation/DotGrid";
import { detailNeed, fieldSkills, isInstance } from "./fields";
import { ChoiceSelect } from "./ChoiceSelect";
import { FreeChoicesFields } from "./FreeChoices";
import { sayable, summary, toSend, type FreePick } from "./freeChoices";
import { applyFilter, byKind, countOf, filterChoices, quickPicks } from "./traitFilter";

/** A new trait for the cart. */
export type NewTrait = {
  category: string;
  name: string;
  detail: string;
  rating: number;
  teacher: string;
  fixed: boolean;
  exception?: Exception;
  /** The free traits chosen with a merit that gives some (see FreeChoices), and them in words. */
  picks?: FreePick[];
  picked?: string;
};

/**
 * Add a trait to one part of the sheet: pick a category from its chips, then from
 * a searchable list of what the character can take there (or everything), see
 * what it costs (priced as it is chosen), and put it in the cart. Traits the rules
 * would refuse are greyed out with the reason. What the character can take counts the cart.
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
  const [teacher, setTeacher] = useState("");
  const [picks, setPicks] = useState<FreePick[]>([]);
  // A trait the rules refuse, asked of staff as an exception.
  const [asking, setAsking] = useState<TraitOut | null>(null);
  const cat = catalogue.categories.find((c) => c.key === category);
  const choices = useChoices(character.id, catalogue, categories, held, lines);
  const current = choices.find((c) => c.key === category);
  const unavailable = current?.refused ?? {};
  const all = current?.traits ?? [];
  const filterable = byKind(all);
  // Held once, unless each is bought on its own with its own name (Retainers).
  const mine = new Set(held.filter((h) => h.category === category && !h.detail && !isInstance(catalogue, h.category, h.name)).map((h) => h.name));
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
  // Skills bought once per field, such as Performance: Singing (MET: VTM p. 92), and
  // a Retainer or identity, each bought with its own name (pp. 98-99, 104).
  const need = detailNeed(trait);
  // After acceptance, discipline dots wait on the home troupe, who will want to know the teacher.
  const asksTeacher = category === "disciplines" && character.home_troupe_id !== null;
  // A merit that gives free traits the player chooses: choose them as it goes in.
  const free = useQuery({
    queryKey: ["free-choices", character.id, category, name],
    enabled: !!trait && !asking,
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/free-choices", { params: { path: { character_id: character.id }, query: { category, name } } })),
  });
  const offers = free.data ?? [];
  const body = { category, name, detail, rating: cat?.rated ? (fixed ?? rating) : null, teacher: asksTeacher ? teacher : "" };
  const priced = !!trait && !!cat?.rated && !asking && (body.rating ?? 0) >= 1;
  const quote = useQuote(character.id, priced, body);
  // On a phone the list grows with the page, so the chosen trait's form is brought into view.
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (name) form.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [name]);

  const choose = (t: TraitOut) => {
    setAsking(null);
    setName(t.name);
    setPicks([]);
    setDetail("");
    setRating(1);
  };
  const add = () => {
    onAdd({
      category,
      name,
      detail,
      rating: body.rating ?? 1,
      teacher: body.teacher,
      fixed: fixed !== null,
      ...(offers.length > 0 && picks.length > 0 ? { picks: toSend(picks), picked: summary(offers, picks) } : {}),
    });
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
      {/* Its own scroll area only on a wider screen: on a phone, one inside the page's is hard to work. */}
      <ul className="flex flex-col sm:max-h-72 sm:overflow-y-auto">
        {matching.map((t) => (
          <TraitChoice
            key={t.name}
            trait={t}
            chosen={t.name === name}
            refused={unavailable[t.name]}
            opened={current?.opened?.[t.name]}
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
          fields={fieldSkills(catalogue)}
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
          ref={form}
          className="flex scroll-mb-20 flex-col gap-3 border-t border-ash pt-3"
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
              <ChoiceSelect required choices={trait.choices} fields={fieldSkills(catalogue)} value={detail} onChange={setDetail} />
            </Field>
          ) : (
            <Field label={need?.label ?? "Detail"} hint={need?.hint ?? "Optional: a specialisation, subject, or name."}>
              <Input required={!!need} placeholder={need?.placeholder} value={detail} onChange={(e) => setDetail(e.target.value)} />
            </Field>
          )}
          {cat?.rated && fixed === null && (
            <Field label="Rating">
              <Input
                type="number"
                min={1}
                max={cat.max_rating ?? undefined}
                value={rating}
                onChange={(e) => setRating(Number(e.target.value))}
              />
            </Field>
          )}
          {asksTeacher && (
            <Field label="Teacher" hint="Out-of-clan powers need a teacher who has them in-clan.">
              <Input value={teacher} onChange={(e) => setTeacher(e.target.value)} />
            </Field>
          )}
          {offers.length > 0 && (
            <>
              <FreeChoicesFields offers={offers} picks={picks} onChange={setPicks} />
              <p className="text-xs text-mist">
                {character.home_troupe_id
                  ? "Choose now: once it is on the sheet, staff change them."
                  : "You can change these on the sheet until a home troupe accepts the character."}
              </p>
            </>
          )}
          {/* A power a merit opens says so: "Hard as Steel: 20 XP." */}
          {quote.data ? (
            <p className="text-sm" aria-live="polite">
              {quote.data.because ? `${quote.data.because}.` : `Costs ${quote.data.cost} XP.`}
            </p>
          ) : (
            priced && !quote.error && <p className="text-sm text-mist">Pricing…</p>
          )}
          <ErrorText error={quote.error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={!sayable(picks, offers)}>
              Add to cart
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

/** How long a choice must stay put before it is priced: a quote judges the whole sheet. */
const SETTLE_MS = 400;

/**
 * What adding the trait would cost, asked once the choice (a rating, a detail typed)
 * has stayed put for a moment, not on every keystroke. Only an answer for the
 * choice as it stands is given.
 */
function useQuote(characterId: string, enabled: boolean, body: { category: string; name: string; detail: string; rating: number | null }) {
  const asked = { category: body.category, name: body.name, detail: body.detail, rating: body.rating, teacher: "" };
  const now = JSON.stringify(asked);
  const [settled, setSettled] = useState(now);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(now), SETTLE_MS);
    return () => clearTimeout(timer);
  }, [now]);
  const quote = useQuery({
    queryKey: ["quote", characterId, now],
    queryFn: ({ signal }) => unwrap(api.POST("/api/characters/{character_id}/quote", { params: { path: { character_id: characterId } }, body: asked, signal })),
    enabled: enabled && settled === now,
    retry: false,
  });
  return enabled ? quote : { data: undefined, error: null };
}

/**
 * One trait in the list: chosen, or greyed with why the rules refuse it, and then
 * (given `onAsk`) a way to ask staff for it as an exception.
 */
function TraitChoice({
  trait,
  chosen,
  refused,
  opened,
  onChoose,
  onAsk,
}: {
  trait: TraitOut;
  chosen: boolean;
  refused?: string;
  /** Opened past the character's Generation by a merit: "Hard as Steel: 20 XP". */
  opened?: string;
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
          {trait.house && <HouseMark label={trait.house.label} summary={trait.house.summary} />}
        </span>
        <HouseSummary summary={trait.house?.summary} />
        {refused && <span className="text-xs text-blood-bright">{refused}</span>}
        {!refused && opened && <span className="text-xs text-gold">{opened}</span>}
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
