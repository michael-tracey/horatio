import { useQuery } from "@tanstack/react-query";
import { HouseMark } from "../../components/HouseMark";
import { useMemo, useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetOut, TraitOut } from "../../api/types";
import { Badge, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction, useUnavailable } from "../../hooks";
import { PrintAndBadge } from "./Badge";
import { CUSTOM_ARCHETYPE, identityChoices } from "./creation/logic";
import { MORALITY, heldMorality, moralityLabel, moralityOptions, moveMorality, willpowerAndHealth } from "./morality";

type Change = { category: string; name: string; rating: number | null };

/** Each attribute, in sheet order, with the category its focus is chosen from (MET: VTM p. 90). */
const ATTRIBUTES: [string, string][] = [
  ["Physical", "focus_physicals"],
  ["Social", "focus_socials"],
  ["Mental", "focus_mentals"],
];

/** Sections of the quick builder after attributes, in sheet order. Long lists get a search box. */
const SECTIONS: { title: string; categories: string[]; split?: boolean; powers?: boolean }[] = [
  { title: "Skills", categories: ["skills"], split: true },
  { title: "Backgrounds", categories: ["backgrounds"] },
  { title: "Disciplines", categories: ["disciplines"] },
  { title: "Techniques", categories: ["techniques"], powers: true },
  { title: "Elder & luminary powers", categories: ["elder_disciplines", "luminary_disciplines"], powers: true },
  { title: "Rituals", categories: ["rituals", "sabbat_rituals"], powers: true },
  { title: "Extra in-clan disciplines", categories: ["extra_in_clan_disciplines"], powers: true },
  { title: "Merits & flaws", categories: ["merits", "flaws"] },
];

/**
 * The fast way to make an NPC: every trait is a row of dots, and tapping a dot
 * sets the rating there and then (tap the top dot again to lower it by one).
 * Nothing is spent; the tally shows what the build would be worth in this
 * troupe.
 */
export function NpcBuilder({ character }: { character: CharacterOut }) {
  const path = { params: { path: { character_id: character.id } } };
  const sheet = useQuery({ queryKey: ["sheet", character.id, null], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", path)) });
  const tally = useQuery({ queryKey: ["tally", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/npc/tally", path)) });
  const catalogue = useQuery({
    queryKey: ["catalogue", character.splat, character.owner_troupe_id],
    queryFn: () =>
      unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: character.splat }, query: { troupe_id: character.owner_troupe_id ?? undefined } } })),
    staleTime: 5 * 60_000,
  });
  const set = useAction((body: Change) => unwrap(api.PUT("/api/characters/{character_id}/npc/ratings", { ...path, body: { ...body, detail: "" } })));

  if (sheet.isPending || catalogue.isPending) return <Loading />;
  if (!sheet.data || !catalogue.data) return <ErrorText error={sheet.error ?? catalogue.error} />;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_16rem]">
      <div className="flex flex-col gap-4">
        <Identity sheet={sheet.data} catalogue={catalogue.data} onChange={(c) => set.mutate(c)} />
        <Attributes sheet={sheet.data} catalogue={catalogue.data} onChange={(c) => set.mutate(c)} />
        {SECTIONS.map((section) => (
          <Section key={section.title} {...section} character={character} sheet={sheet.data} catalogue={catalogue.data} onChange={(c) => set.mutate(c)} />
        ))}
        <Morality sheet={sheet.data} catalogue={catalogue.data} onChange={(c) => set.mutate(c)} />
        <ErrorText error={set.error} />
      </div>
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        {/* Only the troupe's staff see an NPC, and they all print its badge. */}
        <PrintAndBadge character={character} />
        <Card title="Worth">
          <p className="font-display text-3xl text-gold">{tally.data?.total ?? "…"} XP</p>
          <p className="mt-1 text-xs text-mist">What this build would cost a player character here. Starting traits are free.</p>
          {tally.data?.lines.some((l) => l.cost === null) && (
            <ul className="mt-2 text-xs text-blood-bright">
              {tally.data.lines
                .filter((l) => l.cost === null)
                .map((l) => (
                  <li key={l.name}>
                    {l.name}: {l.note}
                  </li>
                ))}
            </ul>
          )}
        </Card>
      </aside>
    </div>
  );
}

function Identity({ sheet, catalogue, onChange }: { sheet: SheetOut; catalogue: CatalogueOut; onChange: (c: Change) => void }) {
  const choices = identityChoices(catalogue, sheet);
  return (
    <Card title="Who">
      <div className="grid gap-3 sm:grid-cols-2">
        {choices.map((c) => (
          <Field key={c.key} label={c.name}>
            <Select
              value={sheet.traits.find((t) => t.category === c.key)?.name ?? ""}
              onChange={(e) => e.target.value && onChange({ category: c.key, name: e.target.value, rating: null })}
            >
              <option value="">Choose…</option>
              {catalogue.traits
                .filter((t) => t.category === c.key && t.name !== CUSTOM_ARCHETYPE)
                .map((t) => (
                  <option key={t.name}>{t.name}</option>
                ))}
            </Select>
          </Field>
        ))}
      </div>
    </Card>
  );
}

/** Attributes as dots, each with its focus beside it: one of three, chosen like a PC's. */
function Attributes({ sheet, catalogue, onChange }: { sheet: SheetOut; catalogue: CatalogueOut; onChange: (c: Change) => void }) {
  const max = catalogue.categories.find((c) => c.key === "attributes")?.max_rating ?? 10;
  return (
    <Card title="Attributes">
      <ul>
        {ATTRIBUTES.map(([name, focusCategory]) => {
          const trait = catalogue.traits.find((t) => t.category === "attributes" && t.name === name);
          if (!trait) return null;
          const options = catalogue.traits.filter((t) => t.category === focusCategory);
          const focus = sheet.traits.find((t) => t.category === focusCategory && (t.rating ?? 0) > 0)?.name ?? "";
          const rating = sheet.traits.find((t) => t.category === "attributes" && t.name === name)?.rating ?? 0;
          return (
            <Row
              key={name}
              trait={trait}
              rating={rating}
              max={max}
              onChange={onChange}
              aside={
                options.length > 0 && (
                  <Select
                    aria-label={`${name} focus`}
                    value={focus}
                    onChange={(e) =>
                      onChange(
                        e.target.value
                          ? { category: focusCategory, name: e.target.value, rating: 1 }
                          : { category: focusCategory, name: focus, rating: 0 },
                      )
                    }
                    className="h-8 w-40 py-0 text-sm"
                  >
                    <option value="">No focus</option>
                    {options.map((o) => (
                      <option key={o.name}>{o.name}</option>
                    ))}
                  </Select>
                )
              }
            />
          );
        })}
      </ul>
    </Card>
  );
}

/**
 * Morality is one choice, Humanity or a single Path, at one rating: choosing
 * another moves the NPC to it, keeping the rating. Willpower and health levels
 * follow as dots.
 */
function Morality({ sheet, catalogue, onChange }: { sheet: SheetOut; catalogue: CatalogueOut; onChange: (c: Change) => void }) {
  // With no Morality held, the choice waits here for its first dot.
  const [chosen, setChosen] = useState<string | null>(null);
  const options = moralityOptions(catalogue);
  const held = heldMorality(sheet, options);
  const name = held.rating ? held.name : (chosen ?? held.name);
  const trait = options.find((t) => t.name === name);
  const rest = willpowerAndHealth(catalogue);
  const maxOf = (category: string) => catalogue.categories.find((c) => c.key === category)?.max_rating ?? 5;
  if (!trait && !rest.length) return null;
  return (
    <Card title="Morality & willpower">
      <ul>
        {trait && (
          <Row
            trait={trait}
            label="Morality"
            rating={held.rating}
            max={maxOf(MORALITY)}
            onChange={onChange}
            aside={
              <Select
                aria-label="Morality"
                value={name}
                onChange={(e) => {
                  const move = moveMorality(held, e.target.value);
                  if (move) onChange(move);
                  else setChosen(e.target.value);
                }}
                className="h-8 w-56 py-0 text-sm"
              >
                {options.map((o) => (
                  <option key={o.name} value={o.name}>
                    {moralityLabel(o.name)}
                  </option>
                ))}
              </Select>
            }
          />
        )}
        {rest.map((t) => (
          <Row
            key={`${t.category}/${t.name}`}
            trait={t}
            rating={sheet.traits.find((s) => s.category === t.category && s.name === t.name)?.rating ?? 0}
            max={maxOf(t.category)}
            onChange={onChange}
          />
        ))}
      </ul>
    </Card>
  );
}

function Section({
  character,
  title,
  categories,
  split,
  powers,
  sheet,
  catalogue,
  onChange,
}: {
  character: CharacterOut;
  title: string;
  categories: string[];
  split?: boolean;
  /** Powers are held or not, in one tap; staff may give any, and one whose prerequisites are unmet is marked. */
  powers?: boolean;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  onChange: (c: Change) => void;
}) {
  const [query, setQuery] = useState("");
  // Why each power not held is out of reach (worked out only while searching, as it is slow), and
  // from the sheet's problems, why each held one is out of order.
  const searching = !!powers && query.trim() !== "";
  const refusedFirst = useUnavailable(character.id, categories[0] ?? "", searching);
  const refusedSecond = useUnavailable(character.id, categories[1] ?? "", searching && categories.length > 1);
  const marks = useMemo(() => {
    const found = new Map<string, string>();
    if (!powers) return found;
    categories.forEach((category, i) => {
      for (const [name, reason] of Object.entries((i === 0 ? refusedFirst.data : refusedSecond.data) ?? {})) found.set(`${category}/${name}`, reason);
    });
    for (const p of sheet.problems) if (categories.includes(p.category)) found.set(`${p.category}/${p.name}`, p.message);
    return found;
  }, [powers, categories, refusedFirst.data, refusedSecond.data, sheet.problems]);
  const ratings = useMemo(() => new Map(sheet.traits.map((t) => [`${t.category}/${t.name}`, t.rating ?? 0])), [sheet]);
  const present = categories.filter((c) => catalogue.categories.some((k) => k.key === c));
  if (!present.length) return null;
  // An archived house merit is not taken anew; one held stays listed.
  const traits = catalogue.traits.filter(
    (t) => present.includes(t.category) && !(t.house?.archived && !ratings.get(`${t.category}/${t.name}`)),
  );
  const q = query.trim().toLowerCase();
  // Long lists show what the NPC has, plus whatever the search finds.
  const long = traits.length > 30;
  const shown = traits.filter((t) => (q ? t.name.toLowerCase().includes(q) : !long || ratings.get(`${t.category}/${t.name}`)));
  const groups = new Map<string, TraitOut[]>();
  for (const t of shown) {
    const heading = split ? (t.attribute ?? "Other") : (catalogue.categories.find((c) => c.key === t.category)?.name ?? t.category);
    groups.set(heading, [...(groups.get(heading) ?? []), t]);
  }
  const order = split ? ["Physical", "Social", "Mental", "Other"] : [...groups.keys()];

  return (
    <Card title={title}>
      {(long || traits.length > 12) && (
        <Input aria-label={`Search ${title}`} placeholder={long ? `Search ${traits.length} to add…` : "Search…"} value={query} onChange={(e) => setQuery(e.target.value)} className="mb-3" />
      )}
      <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {order
          .filter((h) => groups.has(h))
          .map((heading) => (
            <div key={heading}>
              {(groups.size > 1 || split) && <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{heading}</h3>}
              <ul>
                {groups.get(heading)!.map((t) => (
                  <Row
                    key={`${t.category}/${t.name}`}
                    trait={t}
                    rating={ratings.get(`${t.category}/${t.name}`) ?? 0}
                    max={catalogue.categories.find((c) => c.key === t.category)?.max_rating ?? 5}
                    onChange={onChange}
                    power={powers}
                    mark={marks.get(`${t.category}/${t.name}`)}
                  />
                ))}
              </ul>
            </div>
          ))}
      </div>
      {long && !q && shown.length === 0 && <p className="text-sm text-mist">None yet. Search to add some.</p>}
    </Card>
  );
}

function Row({
  trait,
  label,
  rating,
  max,
  onChange,
  aside,
  power,
  mark,
}: {
  trait: TraitOut;
  /** Shown in place of the trait's name, such as Morality before its picker. */
  label?: string;
  rating: number;
  max: number;
  onChange: (c: Change) => void;
  /** Shown beside the name, such as an attribute's focus. */
  aside?: ReactNode;
  /** A power (technique, ritual...): held or not, at its level if it has one. */
  power?: boolean;
  /** Why this one is out of order for the NPC; it is allowed all the same. */
  mark?: string;
}) {
  if (trait.fixed_rating || power) {
    const on = rating > 0;
    const level = trait.fixed_rating ?? 1;
    return (
      <li className="py-1 text-sm">
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={on} onChange={() => onChange({ category: trait.category, name: trait.name, rating: on ? 0 : level })} />
            <span className={on ? "text-parchment" : "text-mist"}>{trait.name}</span>
            {trait.house && <HouseMark label={trait.house.label} short />}
          </label>
          {trait.fixed_rating && <Badge>{trait.fixed_rating}</Badge>}
        </div>
        {mark && (
          <p className="ml-6 text-xs text-blood-bright" data-testid="power-mark">
            {on ? "Marked: " : ""}
            {mark}
          </p>
        )}
      </li>
    );
  }
  // Enough dots to reach the usual ratings in one tap: attributes run to 10.
  const usual = trait.category === "attributes" ? 10 : 5;
  const dots = Math.min(Math.max(usual, rating + 1), max);
  return (
    <li className={`flex flex-wrap items-center justify-between gap-2 text-sm ${aside ? "py-1.5" : "py-0.5"}`}>
      <span className="flex flex-wrap items-center gap-3">
        <span className={`${aside ? "w-16" : ""} ${rating ? "text-parchment" : "text-mist"}`}>{label ?? trait.name}</span>
        {aside}
      </span>
      <span className="flex">
        {Array.from({ length: dots }, (_, i) => i + 1).map((dot) => (
          <button
            key={dot}
            type="button"
            aria-label={`${trait.name} ${dot}`}
            aria-pressed={rating === dot}
            onClick={() => onChange({ category: trait.category, name: trait.name, rating: rating === dot ? dot - 1 : dot })}
            className={`grid h-7 w-5 place-items-center text-base hover:bg-ash sm:w-6 ${dot <= rating ? "text-blood-bright" : "text-mist/60"}`}
          >
            {dot <= rating ? "●" : "○"}
          </button>
        ))}
      </span>
    </li>
  );
}
