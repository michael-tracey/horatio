import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { CatalogueOut, CharacterOut, SheetTraitOut } from "../../api/types";
import { useCatalogue } from "../../catalogue";
import { ChoiceBox, type BoxChoice } from "../../components/ChoiceBox";
import { useClanName } from "../../components/ClanNames";
import { Toggle } from "../../components/Toggle";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, Select } from "../../components/ui";
import { costText, describe, setRating, useCart, type CartLine } from "./cart";
import { ChoiceSelect } from "./ChoiceSelect";
import { useChoices } from "./choices";
import { detailNeed, fieldSkills } from "./fields";
import { rulesTroupe } from "./rules";
import { addableByGroup, useSheet } from "./SheetTab";
import { whenText } from "./xpPlan";

type PlanLine = components["schemas"]["XpPlanLineOut"];
type Kept = components["schemas"]["XpPlanLineIn"];

const kept = (l: Kept): Kept => ({ category: l.category, name: l.name, detail: l.detail, rating: l.rating });
const same = (a: Kept, b: Kept) => a.category === b.category && a.name === b.name && a.detail === b.detail;

/** A planned line as the cart would hold it: from the rating it raises from. */
function asCartLine(l: PlanLine): CartLine {
  return { kind: "set", category: l.category, name: l.name, detail: l.detail, from: l.from_rating, to: l.rating };
}

/**
 * The plan (#1052): traits the player means to buy with XP later, in order, each
 * priced as the cart would price it now, with a running total against the XP
 * unspent and roughly how many games of the troupe's usual award until each is
 * affordable. One tap moves a line that can be bought into the cart. It is the
 * player's own; the staff who see the sheet see it only while it is shared.
 */
export function XpPlan({ character, mine }: { character: CharacterOut; mine: boolean }) {
  const key = ["xp-plan", character.id];
  const client = useQueryClient();
  const plan = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/xp-plan", { params: { path: { character_id: character.id } } })),
    // Staff see it only if it is shared; otherwise there is nothing to show them.
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: { lines: Kept[]; shared: boolean }) =>
      unwrap(api.PUT("/api/characters/{character_id}/xp-plan", { params: { path: { character_id: character.id } }, body })),
    onSuccess: (data) => client.setQueryData(key, data),
  });
  const cart = useCart(character.id);
  const [adding, setAdding] = useState(false);
  const [moved, setMoved] = useState<string | null>(null);

  if (!mine && !plan.data) return null;
  if (plan.isPending) return <Loading />;
  if (plan.error) return <ErrorText error={plan.error} />;
  const p = plan.data;
  const lines = p.lines.map(kept);
  const keep = (next: Kept[], shared = p.shared) => save.mutate({ lines: next, shared });
  const move = (from: number, to: number) => {
    const next = [...lines];
    const [line] = next.splice(from, 1);
    next.splice(to, 0, line!);
    keep(next);
  };
  const toCart = (l: PlanLine, i: number) => {
    cart.update((c) => setRating(c, { category: l.category, name: l.name, detail: l.detail, rating: l.from_rating }, l.rating));
    setMoved(describe(asCartLine(l)));
    keep(lines.filter((_, j) => j !== i));
  };
  const last = p.lines.at(-1);

  return (
    <Card
      title={mine ? "Plan" : "Plan, shared by its player"}
      actions={
        p.mine && (
          <Button variant="ghost" aria-expanded={adding} disabled={save.isPending} onClick={() => setAdding(!adding)}>
            {adding ? "Close" : "Add to plan"}
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        {p.mine ? "What you mean to buy next, in order" : "What its player means to buy next, in order"}, each priced as the cart would price it now.{" "}
        {p.balance} XP unspent
        {p.award ? `; about ${p.award.per_game} XP a game, from ${p.award.source}.` : "."}
      </p>
      {!p.priced && <Notice>Prices aren't worked out while you view as someone.</Notice>}
      {adding && (
        <AddToPlan
          character={character}
          planned={p.lines}
          onAdd={(line) => {
            keep([...lines, line]);
            setAdding(false);
          }}
          onClose={() => setAdding(false)}
        />
      )}
      {moved && (
        <Notice>
          {moved} is in the cart.{" "}
          <Link to={`/characters/${character.id}`} className="underline hover:text-parchment">
            Spend XP on the sheet
          </Link>
          .
        </Notice>
      )}
      {p.lines.length === 0 ? (
        !adding && <p className="text-sm text-mist">Nothing planned yet.</p>
      ) : (
        <ol aria-label="Planned purchases" className="divide-y divide-ash">
          {p.lines.map((l, i) => {
            const what = describe(asCartLine(l));
            return (
              <li key={`${l.category}/${l.name}/${l.detail}/${l.rating}`} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                <div className="min-w-0 text-sm">
                  <p>
                    <span className="text-parchment">{l.held ? `${l.detail ? `${l.name}: ${l.detail}` : l.name} ${l.rating}` : what}</span>
                    {l.cost != null && <span className="text-gold"> · {costText(l.cost) || "no XP"}</span>}
                    {!l.held && l.cost != null && <span className="text-mist"> · {l.total} XP in all</span>}
                  </p>
                  {l.refused ? (
                    <p className="text-xs text-blood-bright">{l.refused}</p>
                  ) : (
                    p.priced && <p className={`text-xs ${l.affordable ? "text-gold" : "text-mist"}`}>{whenText(l, p.balance)}</p>
                  )}
                  {l.because && <p className="text-xs text-mist">{l.because}.</p>}
                  {l.teacher && <p className="text-xs text-mist">Needs a teacher ({l.teacher.rule}), chosen in the cart.</p>}
                  {l.needs_approval && !l.refused && <p className="text-xs text-mist">Waits on the home troupe once bought.</p>}
                </div>
                {p.mine && (
                  <div className="flex shrink-0 flex-wrap items-center gap-1">
                    {l.buyable && (
                      <Button variant="secondary" className="min-h-9" disabled={save.isPending} onClick={() => toCart(l, i)} aria-label={`Move ${what} to the cart`}>
                        Move to cart
                      </Button>
                    )}
                    <Button variant="ghost" className="min-h-9 px-2" disabled={i === 0 || save.isPending} onClick={() => move(i, i - 1)} aria-label={`Move ${what} up`}>
                      ↑
                    </Button>
                    <Button
                      variant="ghost"
                      className="min-h-9 px-2"
                      disabled={i === p.lines.length - 1 || save.isPending}
                      onClick={() => move(i, i + 1)}
                      aria-label={`Move ${what} down`}
                    >
                      ↓
                    </Button>
                    <Button
                      variant="ghost"
                      className="min-h-9 px-2"
                      disabled={save.isPending}
                      onClick={() => keep(lines.filter((_, j) => j !== i))}
                      aria-label={`Take ${what} out of the plan`}
                    >
                      ✕
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {last && p.priced && <p className="mt-2 text-sm">All of it: {last.total} XP.</p>}
      <ErrorText error={save.error} />
      {p.mine && (
        <Toggle
          label="Share with staff"
          hint="The staff who see the sheet see this plan too. Off, only you do."
          checked={p.shared}
          disabled={save.isPending}
          onChange={(on) => keep(lines, on)}
          className="mt-3 border-t border-ash"
        />
      )}
    </Card>
  );
}

/**
 * Choose a trait for the plan, and the rating to take it to: from the explaining
 * drop-down (ChoiceBox) of a category's traits, those held showing the rating the
 * plan leaves them at. What the character can't take is greyed with the reason,
 * judged on the sheet as the plan before it would leave it.
 */
function AddToPlan(props: { character: CharacterOut; planned: PlanLine[]; onAdd: (line: Kept) => void; onClose: () => void }) {
  const catalogue = useCatalogue(props.character.splat, rulesTroupe(props.character));
  const sheet = useSheet(props.character.id);
  if (catalogue.isPending || sheet.isPending) return <Loading compact />;
  if (catalogue.error || sheet.error) return <ErrorText error={catalogue.error ?? sheet.error} />;
  return <PlanPicker {...props} catalogue={catalogue.data} held={sheet.data.traits} />;
}

function PlanPicker({
  character,
  catalogue,
  held,
  planned,
  onAdd,
  onClose,
}: {
  character: CharacterOut;
  catalogue: CatalogueOut;
  held: SheetTraitOut[];
  planned: PlanLine[];
  onAdd: (line: Kept) => void;
  onClose: () => void;
}) {
  const named = useClanName();
  const categories = [...addableByGroup(catalogue).values()].flat();
  const [category, setCategory] = useState(categories[0] ?? "");
  const [chosen, setChosen] = useState<{ name: string; detail: string } | null>(null);
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const lines = planned.filter((l) => !l.held).map(asCartLine);
  const choices = useChoices(character.id, catalogue, [category], held, lines);
  const current = choices[0];
  const cat = catalogue.categories.find((c) => c.key === category);
  // The rating each trait is at once the plan so far is bought.
  const at = (name: string, d: string) =>
    Math.max(
      held.find((h) => h.category === category && h.name === name && h.detail === d)?.rating ?? 0,
      ...planned.filter((l) => same(l, { category, name, detail: d, rating: 0 })).map((l) => l.rating),
    );
  // Held with a detail of its own (Performance: Singing, a Retainer by name): raised as it is.
  const heldDetailed = held.filter((h) => h.category === category && h.detail);
  const traits = current?.traits ?? [];
  const boxed: BoxChoice[] = [
    ...heldDetailed.map((h) => ({ value: `${h.name}\u0001${h.detail}`, label: `${h.name}: ${h.detail}`, name: h.name, mark: `at ${at(h.name, h.detail)}` })),
    ...traits.map((t): BoxChoice => {
      const now = at(t.name, "");
      const refused = now ? undefined : current?.refused[t.name];
      return { value: t.name, label: t.name, trait: t, mark: now ? `at ${now}` : undefined, disabled: !!refused, note: refused };
    }),
  ];
  const trait = chosen ? traits.find((t) => t.name === chosen.name) : undefined;
  const fixed = trait?.fixed_rating ?? null;
  // A new one bought by field or by name needs its detail (a held one has it).
  const need = chosen && !chosen.detail ? detailNeed(trait) : null;
  const choicesOf = chosen && !chosen.detail ? trait?.choices : null;
  const finalDetail = chosen?.detail || detail.trim();
  const from = chosen ? at(chosen.name, finalDetail) : 0;
  const to = fixed ?? rating;
  const max = cat?.max_rating ?? undefined;
  const ready = !!chosen && to > from && (!max || to <= max) && (!(need || choicesOf) || !!finalDetail);

  const choose = (value: string) => {
    const [name, d = ""] = value.split("\u0001");
    setChosen({ name: name!, detail: d });
    setDetail("");
    setRating(at(name!, d) + 1);
  };

  return (
    <form
      aria-label="Add to plan"
      className="mb-4 flex flex-col gap-3 rounded-md border border-ash bg-night/40 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (chosen && ready) onAdd({ category, name: chosen.name, detail: finalDetail, rating: to });
      }}
    >
      <div className="flex flex-wrap gap-2">
        <Select
          aria-label="Category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setChosen(null);
          }}
          className="w-auto"
        >
          {categories.map((key) => (
            <option key={key} value={key}>
              {catalogue.categories.find((c) => c.key === key)?.name ?? key}
            </option>
          ))}
        </Select>
        <ChoiceBox
          label={`Plan ${cat?.name ?? ""}`}
          placeholder={current?.ready ? `Search ${cat?.name ?? ""}…` : "Checking what can be taken…"}
          value={chosen ? (chosen.detail ? `${chosen.name}: ${chosen.detail}` : chosen.name) : undefined}
          choices={boxed}
          onChoose={choose}
          splat={character.splat}
          troupeId={rulesTroupe(character)}
          className="min-w-40 flex-1"
        />
      </div>
      {chosen && (
        <>
          {choicesOf ? (
            <Field label="Which?" hint={`${named(chosen.name)} gives one of these.`}>
              <ChoiceSelect required choices={choicesOf} fields={fieldSkills(catalogue)} value={detail} onChange={setDetail} />
            </Field>
          ) : (
            need && (
              <Field label={need.label} hint={need.hint}>
                <Input required placeholder={need.placeholder} value={detail} onChange={(e) => setDetail(e.target.value)} />
              </Field>
            )
          )}
          {fixed === null && (
            <Field label="Up to" hint={from ? `At ${from} once the plan before it is bought.` : undefined}>
              <Input type="number" min={from + 1} max={max} value={rating} onChange={(e) => setRating(Number(e.target.value))} className="w-24" />
            </Field>
          )}
        </>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={!ready}>
          Add to plan
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
