import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetOut, TraitOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { identityChoices } from "./creation/logic";

type Change = { category: string; name: string; rating: number | null };

/** Sections of the quick builder, in sheet order. Long lists get a search box. */
const SECTIONS: { title: string; categories: string[]; split?: boolean }[] = [
  { title: "Attributes", categories: ["attributes"] },
  { title: "Focuses", categories: ["focus_physicals", "focus_mentals", "focus_socials"] },
  { title: "Skills", categories: ["skills"], split: true },
  { title: "Backgrounds", categories: ["backgrounds"] },
  { title: "Disciplines", categories: ["disciplines"] },
  { title: "Merits & flaws", categories: ["merits", "flaws"] },
  { title: "Morality & willpower", categories: ["paths", "willpower_sources", "health_levels"] },
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
        {SECTIONS.map((section) => (
          <Section key={section.title} {...section} sheet={sheet.data} catalogue={catalogue.data} onChange={(c) => set.mutate(c)} />
        ))}
        <ErrorText error={set.error} />
      </div>
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
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
        <DeleteNpc character={character} />
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
                .filter((t) => t.category === c.key)
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

function Section({
  title,
  categories,
  split,
  sheet,
  catalogue,
  onChange,
}: {
  title: string;
  categories: string[];
  split?: boolean;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  onChange: (c: Change) => void;
}) {
  const [query, setQuery] = useState("");
  const ratings = useMemo(() => new Map(sheet.traits.map((t) => [`${t.category}/${t.name}`, t.rating ?? 0])), [sheet]);
  const present = categories.filter((c) => catalogue.categories.some((k) => k.key === c));
  if (!present.length) return null;
  const traits = catalogue.traits.filter((t) => present.includes(t.category));
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
                  <Row key={`${t.category}/${t.name}`} trait={t} rating={ratings.get(`${t.category}/${t.name}`) ?? 0} max={catalogue.categories.find((c) => c.key === t.category)?.max_rating ?? 5} onChange={onChange} />
                ))}
              </ul>
            </div>
          ))}
      </div>
      {long && !q && shown.length === 0 && <p className="text-sm text-mist">None yet. Search to add some.</p>}
    </Card>
  );
}

function Row({ trait, rating, max, onChange }: { trait: TraitOut; rating: number; max: number; onChange: (c: Change) => void }) {
  if (trait.fixed_rating) {
    const on = rating > 0;
    return (
      <li className="flex items-center justify-between gap-2 py-1 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={on} onChange={() => onChange({ category: trait.category, name: trait.name, rating: on ? 0 : trait.fixed_rating! })} />
          <span className={on ? "text-parchment" : "text-mist"}>{trait.name}</span>
        </label>
        <Badge>{trait.fixed_rating}</Badge>
      </li>
    );
  }
  // Enough dots to reach the usual ratings in one tap: attributes run to 10.
  const usual = trait.category === "attributes" ? 10 : 5;
  const dots = Math.min(Math.max(usual, rating + 1), max);
  return (
    <li className="flex items-center justify-between gap-2 py-0.5 text-sm">
      <span className={rating ? "text-parchment" : "text-mist"}>{trait.name}</span>
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

function DeleteNpc({ character }: { character: CharacterOut }) {
  const navigate = useNavigate();
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/characters/{character_id}", { params: { path: { character_id: character.id } } }));
    navigate(`/troupes/${character.owner_troupe_id}/npcs`);
  });
  return (
    <>
      <Button
        variant="danger"
        onClick={() => {
          if (window.confirm(`Delete the NPC ${character.name}? This cannot be undone.`)) remove.mutate(undefined);
        }}
      >
        Delete this NPC
      </Button>
      <ErrorText error={remove.error} />
    </>
  );
}
