import { useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, PoolOut, SheetOut, TraitOut } from "../../../api/types";
import { Badge, ErrorText, Select } from "../../../components/ui";
import { useAction, useRefusals } from "../../../hooks";
import { FreeChoicesStep } from "./FreeChoicesStep";
import { Because } from "./Because";
import type { StepRef } from "./notices";

export type FromMeritsProps = {
  character: CharacterOut;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  /** The merits (or flaws) that change this step. */
  traits: { category: string; name: string }[];
  /** The choices to offer for some of them, in place of the catalogue's (Inept: the in-clan disciplines). */
  choices?: Record<string, string[]>;
  /** The wizard's steps, and this one: a refusal names the traits it is because of, linking to their steps. */
  steps?: StepRef[];
  step?: StepRef;
};

/**
 * Merits or flaws whose point is a choice on an earlier step, taken from that step
 * as well as from Merits & flaws (#192). Each comes from its budget, and Merits &
 * flaws shows it as taken. What the character can take, and why not, is the
 * server's to say: what nothing could allow (another clan's merit) is left out.
 */
export function FromMerits({ character, creation, sheet, catalogue, traits, choices, steps, step }: FromMeritsProps) {
  const categories = [...new Set(traits.map((t) => t.category))];
  const pools = categories
    .map((category) => creation.pools.find((p) => p.category === category && p.kind === "points"))
    .filter((p): p is PoolOut => !!p);
  if (!pools.length) return null;
  const title = categories.every((c) => c === "merits") ? "From merits" : "From merits and flaws";
  return (
    <section aria-label={title} className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <h3 className="text-sm text-parchment">{title}</h3>
      {pools.map((pool) => (
        <FromBudget
          key={pool.category}
          character={character}
          pool={pool}
          sheet={sheet}
          choices={choices}
          steps={steps}
          step={step}
          traits={traits
            .filter((t) => t.category === pool.category)
            .map((t) => catalogue.traits.find((c) => c.category === t.category && c.name === t.name))
            .filter((t): t is TraitOut => !!t)}
        />
      ))}
    </section>
  );
}

function FromBudget({
  character,
  pool,
  sheet,
  traits: catalogued,
  choices: offered,
  steps,
  step,
}: {
  character: CharacterOut;
  pool: PoolOut;
  sheet: SheetOut;
  traits: TraitOut[];
  choices?: Record<string, string[]>;
  steps?: StepRef[];
  step?: StepRef;
}) {
  const traits = catalogued.map((t) => (offered?.[t.name] ? { ...t, choices: offered[t.name] } : t));
  const barred = useRefusals(character.id, pool.category, true, { asIf: "empty" });
  const refusals = useRefusals(character.id, pool.category).data ?? {};
  // A choice the merit asks for (Bonds of Stolen Vitae: which discipline), before it is taken.
  const [choices, setChoices] = useState<Record<string, string>>({});
  const held = (name: string) => sheet.traits.find((t) => t.category === pool.category && t.name === name && (t.rating ?? 0) > 0);
  const change = useAction(async ({ trait, on }: { trait: TraitOut; on: boolean }) => {
    const path = { params: { path: { character_id: character.id } } };
    const points = trait.fixed_rating ?? 1;
    if (on) {
      const detail = choices[trait.name] ?? "";
      return unwrap(api.PUT("/api/characters/{character_id}/creation/picks", { ...path, body: { category: pool.category, name: trait.name, detail, rating: points } }));
    }
    const detail = held(trait.name)?.detail ?? "";
    if (pool.traits.some((t) => t.name === trait.name))
      return unwrap(api.POST("/api/characters/{character_id}/creation/picks/remove", { ...path, body: { category: pool.category, name: trait.name, detail } }));
    // Taken some other way than from the budget (bought on the Sheet tab): taken off.
    return unwrap(api.PUT("/api/characters/{character_id}/traits", { ...path, body: { category: pool.category, name: trait.name, detail, rating: 0, teacher: "" } }));
  });
  if (!barred.data) return null;
  // What nothing could allow (another clan's merit) is left out; what a pick on this step
  // could put right (a Generation that Thin Blooded is refused for) is shown, with why.
  const here = new Set(step?.categories ?? []);
  const fixable = (name: string) => {
    const why = barred.data![name];
    return !!why && why.because.length > 0 && why.because.every((b) => here.has(b.category));
  };
  const shown = traits.filter((t) => held(t.name) || !(t.name in barred.data!) || fixable(t.name));
  if (!shown.length) return null;
  const kind = pool.category === "flaws" ? "flaw" : "merit";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-xs text-mist">
        <span>Taken from the same {pool.category_name.toLowerCase()} budget as on Merits &amp; flaws.</span>
        <Badge tone={pool.remaining > 0 ? "gold" : "mist"}>
          {pool.used} of {pool.allowed} points
        </Badge>
      </div>
      <ul className="flex flex-col gap-2">
        {shown.map((t) => {
          const mine = held(t.name);
          const points = t.fixed_rating ?? 1;
          const refusal = mine ? undefined : (refusals[t.name] ?? (fixable(t.name) ? barred.data![t.name] : undefined));
          const refused = refusal?.message;
          const short = !mine && points > pool.remaining;
          const unchosen = !mine && !!t.choices?.length && !choices[t.name];
          const id = `from-${pool.category}-${t.name}`.replace(/\W+/g, "-");
          return (
            <li key={t.name} className="flex flex-col gap-1 text-sm">
              <div className="flex items-start gap-2">
                <input
                  id={id}
                  type="checkbox"
                  role="switch"
                  className="mt-1"
                  checked={!!mine}
                  disabled={change.isPending || (!mine && (!!refused || short || unchosen))}
                  onChange={(e) => change.mutate({ trait: t, on: e.target.checked })}
                  aria-describedby={t.description ? `${id}-about` : undefined}
                />
                <div className="min-w-0">
                  {/* Named by the merit alone: its description is read as its description. */}
                  <label htmlFor={id}>
                    <span className="text-parchment">{t.name}</span>{" "}
                    <span className="text-gold">
                      ({points}-point {kind}
                      {t.page_reference ? `, p. ${t.page_reference}` : ""})
                    </span>
                    {mine?.detail && <span className="text-parchment">: {mine.detail}</span>}
                  </label>
                  {t.description && (
                    <p id={`${id}-about`} className="mt-0.5 text-xs text-mist">
                      {t.description}
                    </p>
                  )}
                </div>
              </div>
              {!mine && !!t.choices?.length && (
                <Select
                  aria-label={`${t.name}: which?`}
                  className="ml-6 h-8 w-auto py-0"
                  value={choices[t.name] ?? ""}
                  onChange={(e) => setChoices({ ...choices, [t.name]: e.target.value })}
                >
                  <option value="">Which?</option>
                  {t.choices.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              )}
              {refused && (
                <p className="ml-6 text-xs text-blood-bright">
                  {refused}
                  {steps && step && <Because characterId={character.id} refs={refusal!.because} steps={steps} step={step} />}
                </p>
              )}
              {mine && <FreeChoicesHere character={character} sheet={sheet} category={pool.category} name={t.name} />}
              {!refused && short && (
                <p className="ml-6 text-xs text-mist">
                  Needs {points} points; {pool.remaining} left.
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <ErrorText error={change.error} />
    </div>
  );
}

/** The free traits a held merit gives, chosen under it. */
function FreeChoicesHere({ character, sheet, category, name }: { character: CharacterOut; sheet: SheetOut; category: string; name: string }) {
  const trait = sheet.traits.find((t) => t.category === category && t.name === name && (t.free_choices ?? []).length > 0);
  if (!trait) return null;
  return <FreeChoicesStep character={character} trait={trait} />;
}
