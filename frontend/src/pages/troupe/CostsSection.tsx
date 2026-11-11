import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CostCategoryOut, CostOut, CostsOut } from "../../api/types";
import { withClanNames } from "../../clanNames";
import { useClanName } from "../../components/ClanNames";
import { Explainer } from "../../components/Explainer";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { RULES_QUERY, useRulesAction } from "../../hooks";
import { pageText } from "./bookPage";
import { useHouseSplat } from "./HouseSplat";
import { FACTS, flat, linesOf, newLine, overlaps, parseTable, previewRatings, priceAt, sameCondition, SCHEMES, TESTS, toCondition } from "./costs";
import type { Fact, Line, Pricing, Scheme } from "./costs";

/** What a price is about, in a few words: "Path of Blood, Assamite clan". */
function subject(cost: CostOut, category: CostCategoryOut | undefined): string {
  const what = cost.trait ?? `All ${category?.name ?? cost.category}`;
  return cost.condition_text ? `${what}, ${cost.condition_text}` : what;
}

/** An editor's target: a new price, a rule set price to replace, or a troupe price to change. */
type Editing =
  | { kind: "new" }
  | { kind: "replace"; cost: CostOut }
  | { kind: "change"; cost: CostOut };

/**
 * The rule set's prices and this troupe's own. A troupe price applies to
 * characters whose home troupe this is, or who are being built for it, from
 * their next purchase; what they have already bought keeps what it cost.
 */
export function CostsSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const [onlyOurs, setOnlyOurs] = useState(false);
  const [query, setQuery] = useState("");
  const { splat, picker } = useHouseSplat(troupeId);
  const named = useClanName();
  const costs = useQuery({
    queryKey: ["costs", troupeId, splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/costs", { params: { path: { troupe_id: troupeId }, query: { splat } } })),
  });
  const remove = useRulesAction((id: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/costs/{cost_id}", { params: { path: { troupe_id: troupeId, cost_id: id }, query: { splat } } })),
  );
  if (costs.isPending) return <Loading />;
  if (costs.error) return <ErrorText error={costs.error} />;

  const categories = new Map(costs.data.categories.map((c) => [c.key, c]));
  const q = query.trim().toLowerCase();
  const shown = costs.data.costs.filter(
    (c) =>
      categories.has(c.category) &&
      (!onlyOurs || c.house) &&
      (!q || withClanNames(`${categories.get(c.category)?.name} ${subject(c, categories.get(c.category))}`).toLowerCase().includes(q)),
  );
  const groups = new Map<string, CostOut[]>();
  for (const c of shown) groups.set(c.category, [...(groups.get(c.category) ?? []), c]);
  // Categories the rule set simply gives away (focuses, specialisations) are listed together.
  const free = [...groups].filter(([, rows]) => rows.every((c) => !c.house && !c.trait && !c.condition && c.scheme === "free"));
  for (const [key] of free) groups.delete(key);
  const ours = costs.data.costs.filter((c) => c.house).length;

  return (
    <div className="flex flex-col gap-6">
      {picker}
      <Explainer id="rules-costs" title="How costs work">
        <p className="text-sm">
          Each price below comes from the rule set, with the book page where it names one trait. When several could
          apply, the most specific wins: a price for one trait beats one for its whole category, and a price with more
          conditions beats one with fewer. A price of this troupe's wins a tie.
        </p>
        <p className="mt-2 text-sm text-mist">
          A troupe price can be only for some characters: by their Generation background, whether the trait is in-clan, or
          their clan. A price with the same condition as the rule set's replaces it.
        </p>
        <p className="mt-2 text-sm text-mist">
          A troupe price applies to characters whose home troupe this is, or who are being built for it, from their next
          purchase. What they have already bought keeps what it cost.
        </p>
      </Explainer>

      {editing && (
        <PriceEditor key={JSON.stringify(editing)} troupeId={troupeId} splat={splat} data={costs.data} editing={editing} onClose={() => setEditing(null)} />
      )}

      <Card
        title="Costs"
        actions={
          canEdit &&
          !editing && (
            <Button variant="secondary" onClick={() => setEditing({ kind: "new" })}>
              Add a price
            </Button>
          )
        }
      >
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Input
            aria-label="Search costs"
            placeholder="Search costs…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-48 flex-1"
          />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyOurs} onChange={(e) => setOnlyOurs(e.target.checked)} />
            Only house rules ({ours})
          </label>
        </div>
        {shown.length === 0 && <p className="text-sm text-mist">No prices match.</p>}
        <div className="flex flex-col gap-5">
          {[...groups].map(([key, rows]) => {
            const category = categories.get(key);
            return (
              <section key={key}>
                <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{category?.name ?? key}</h3>
                <ul className="divide-y divide-ash">
                  {rows.map((c) => (
                    <li key={c.id ?? `${c.trait}-${JSON.stringify(c.condition)}`} className="flex items-center gap-3 py-2.5 sm:gap-4">
                      <span className={`min-w-0 flex-1 text-sm ${c.replaced ? "text-mist line-through" : ""}`}>
                        <span className={c.replaced ? "" : "text-parchment"}>{named(subject(c, category))}</span>
                        {": "}
                        <span>{c.price_text}</span>
                        {c.page && <span className="text-mist"> {pageText(c.page)}</span>}
                        {c.text && <span className="block text-xs text-mist no-underline">House rule: {c.text}</span>}
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {c.house && <Badge tone="gold">House rule</Badge>}
                        {c.replaced && <Badge>Replaced here</Badge>}
                        {canEdit && c.house && c.id && (
                          <>
                            <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing({ kind: "change", cost: c })}>
                              Change
                            </Button>
                            <Button
                              variant="ghost"
                              className="min-h-8 px-2"
                              aria-label={`Remove the price for ${named(subject(c, category))}`}
                              onClick={() => remove.mutate(c.id!)}
                            >
                              Remove
                            </Button>
                          </>
                        )}
                        {canEdit && !c.house && !c.replaced && (c.trait !== null || !category?.per_trait) && (
                          <Button
                            variant="secondary"
                            className="min-h-8 px-3"
                            aria-label={`Change the price for ${named(subject(c, category))}`}
                            onClick={() => setEditing({ kind: "replace", cost: c })}
                          >
                            Change
                          </Button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
          {free.length > 0 && (
            <section>
              <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Free</h3>
              <p className="py-2.5 text-sm">
                {free.map(([key]) => categories.get(key)?.name ?? key).join(", ")}.
                {canEdit && <span className="text-mist"> To price one of these, add a price for it.</span>}
              </p>
            </section>
          )}
        </div>
        <ErrorText error={remove.error} />
      </Card>
    </div>
  );
}

function PriceEditor({ troupeId, splat, data, editing, onClose }: { troupeId: string; splat: string; data: CostsOut; editing: Editing; onClose: () => void }) {
  const start = editing.kind === "new" ? null : editing.cost;
  const named = useClanName();
  const [category, setCategory]
 = useState(start?.category ?? data.categories[0]?.key ?? "");
  const [trait, setTrait] = useState(start?.trait ?? "");
  const [scheme, setScheme] = useState<Scheme>(start?.scheme ?? "per_dot");
  const [rate, setRate] = useState(start?.rate?.toString() ?? "");
  const [table, setTable] = useState(start?.table?.join(", ") ?? "");
  const [text, setText] = useState(editing.kind === "change" ? (editing.cost.text ?? "") : "");
  // A price replacing the rule set's keeps its condition, as does one the lines cannot say.
  const replacesBook =
    editing.kind === "replace" ||
    (editing.kind === "change" &&
      data.costs.some((c) => !c.house && c.category === editing.cost.category && c.trait === editing.cost.trait && sameCondition(c.condition, editing.cost.condition)));
  const startLines = linesOf(start?.condition);
  const fixedCondition = replacesBook || startLines === null;
  const [lines, setLines] = useState<Line[]>(startLines ?? []);
  const cat = data.categories.find((c) => c.key === category);
  const catalogue = useQuery({
    // The rule set's own catalogue, for the book ratings of merits and flaws and the clans.
    queryKey: ["catalogue", splat, null],
    meta: RULES_QUERY,
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: {} } })),
  });
  const clans = (catalogue.data?.traits ?? []).filter((t) => t.category === "clan").map((t) => t.name);
  const traits = (catalogue.data?.traits ?? []).filter((t) => t.category === category).map((t) => t.name);
  // A merit or flaw held at one rating, by the book: a fixed price here is its value.
  const bookRating =
    start?.fixed_rating ?? catalogue.data?.traits.find((t) => t.category === category && t.name === trait)?.fixed_rating ?? null;

  const pricing: Pricing = {
    scheme,
    rate: rate.trim() === "" ? null : Number(rate),
    table: scheme === "table" ? parseTable(table) : null,
  };
  const built = fixedCondition ? { condition: start?.condition ?? null } : toCondition(lines);
  const condition = "condition" in built ? built.condition : null;
  const body = { scheme, rate: pricing.rate, table: pricing.table, text };
  const save = useRulesAction(async () => {
    if (editing.kind === "change") {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/costs/{cost_id}", {
          params: { path: { troupe_id: troupeId, cost_id: editing.cost.id! }, query: { splat } },
          body: fixedCondition ? body : { ...body, condition },
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/costs", {
          params: { path: { troupe_id: troupeId }, query: { splat } },
          body: { ...body, category, trait: trait || null, condition },
        }),
      );
    }
    onClose();
  });

  const target = { category, trait: trait || null, condition };
  const { replaces, stillApplies } = overlaps(target, data.costs);
  const ratings = flat(pricing) ? [1] : previewRatings(cat?.max_rating ?? null);
  const needsRate = scheme === "per_dot" || scheme === "progressive" || scheme === "fixed";
  const ready =
    !!category &&
    (!cat?.per_trait || !!trait) &&
    (!needsRate || pricing.rate !== null) &&
    (scheme !== "table" || pricing.table !== null) &&
    "condition" in built;
  const unit = cat?.unit ?? "dot";
  const title =
    editing.kind === "new" ? "Add a price" : `Price for ${named(subject(editing.cost, cat))}`;

  return (
    <Card title={title}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        {editing.kind === "new" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Category">
              <Select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setTrait("");
                }}
              >
                {data.categories.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Trait" hint={cat?.per_trait ? `${cat.name} are priced one at a time.` : "Leave empty to price the whole category."}>
              <Input list="price-traits" value={trait} onChange={(e) => setTrait(e.target.value)} placeholder="Search…" />
            </Field>
            <datalist id="price-traits">
              {traits.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="How it's priced">
            <Select value={scheme} onChange={(e) => setScheme(e.target.value as Scheme)}>
              {SCHEMES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          {needsRate && (
            <Field label={scheme === "fixed" ? "XP" : `XP per ${unit}`} hint={unit === "point" && category === "flaws" ? "Flaws give XP back: use a negative amount." : undefined}>
              <Input type="number" value={rate} onChange={(e) => setRate(e.target.value)} />
            </Field>
          )}
          {scheme === "table" && (
            <Field label={`XP for each ${unit} in turn`} hint="For example: 1, 4, 6, 8, 10">
              <Input value={table} onChange={(e) => setTable(e.target.value)} />
            </Field>
          )}
        </div>
        {fixedCondition ? (
          start?.condition_text && (
            <p className="text-sm">
              <span className="text-mist">Only for: </span>
              {named(start.condition_text)}
              {replacesBook && <span className="text-mist"> (the rule set's condition, which a price replacing it keeps)</span>}
            </p>
          )
        ) : (
          <ConditionLines lines={lines} onChange={setLines} facts={data.facts ?? []} clans={clans} problem={"problem" in built ? built.problem : null} />
        )}
        {bookRating !== null && (
          <p className="text-sm text-mist">
            {trait} is always held at one rating ({bookRating} by the book). A fixed price here is also its value in this troupe: the
            rating it is held at, and what it counts toward the points limit and the starting points.
            {scheme !== "fixed" && " Only a fixed price changes its rating."}
          </p>
        )}
        <Field label="Note for players" hint="Shown with the trait as “House rule: …”. Optional.">
          <Input value={text} onChange={(e) => setText(e.target.value)} />
        </Field>

        <div className="overflow-x-auto">
          <table className="text-sm">
            <thead>
              <tr className="text-left text-xs text-mist">
                <th className="pr-4 font-normal">{flat(pricing) ? "" : unit === "point" ? "Points" : "Dots"}</th>
                {ratings.map((r) => (
                  <th key={r} className="px-2 text-right font-normal">
                    {flat(pricing) ? "Price" : r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(editing.kind === "change" ? [editing.cost] : replaces).map((c) => (
                <PreviewRow key={`was-${c.id ?? JSON.stringify(c.condition)}-${c.trait}`} label={editing.kind === "change" ? "Now" : "As written"} pricing={c} ratings={ratings} />
              ))}
              <PreviewRow label="With the change" pricing={pricing} ratings={ratings} strong />
            </tbody>
          </table>
        </div>
        {stillApplies.length > 0 && (
          <p className="text-xs text-mist">
            More specific prices still apply:{" "}
            {stillApplies.map((c) => `${named(subject(c, cat))} (${c.price_text})`).join("; ")}.
          </p>
        )}

        <ErrorText error={save.error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={!ready || save.isPending}>
            Save price
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

/**
 * "Only for…": the lines of a price's condition, each a fact, a test and a value.
 * With none, the price is for every character.
 */
function ConditionLines({
  lines,
  onChange,
  facts,
  clans,
  problem,
}: {
  lines: Line[];
  onChange: (lines: Line[]) => void;
  facts: string[];
  clans: string[];
  problem: string | null;
}) {
  const named = useClanName();
  const offered = FACTS.filter((f) => facts.includes(f.value));
  const families = [...new Set(clans.map((c) => (c.split(":")[0] ?? c).trim()))];
  const set = (i: number, line: Line) => onChange(lines.map((l, j) => (j === i ? line : l)));
  const small = "h-8 w-auto py-0 text-sm";
  if (offered.length === 0) return null;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm">
        Only for… <span className="text-mist">{lines.length ? "characters who meet all of these" : "every character, unless you add a condition"}</span>
      </legend>
      {lines.map((line, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 rounded-md border border-ash/60 px-2 py-1.5">
          <Select aria-label={`Condition ${i + 1}`} value={line.fact} onChange={(e) => set(i, newLine(e.target.value as Fact))} className={small}>
            {offered.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </Select>
          {line.fact === "generation" ? (
            <>
              <Select aria-label={`Condition ${i + 1}: how`} value={line.test} onChange={(e) => set(i, { ...line, test: e.target.value as Line["test"] })} className={small}>
                {TESTS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
              <Select aria-label={`Condition ${i + 1}: rating`} value={line.value} onChange={(e) => set(i, { ...line, value: e.target.value })} className={small}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={String(n)}>
                    {n}
                  </option>
                ))}
              </Select>
            </>
          ) : line.fact === "in_clan" ? (
            <Select aria-label={`Condition ${i + 1}: in-clan`} value={line.value} onChange={(e) => set(i, { ...line, value: e.target.value })} className={small}>
              <option value="true">yes</option>
              <option value="false">no (out-of-clan)</option>
            </Select>
          ) : (
            <>
              <span className="text-sm text-mist">is</span>
              <Select aria-label={`Condition ${i + 1}: clan`} value={line.value} onChange={(e) => set(i, { ...line, value: e.target.value })} className={small}>
                <option value="">Choose…</option>
                {(line.fact === "clan" ? clans : families).map((name) => (
                  <option key={name} value={name}>
                    {named(name)}
                  </option>
                ))}
              </Select>
            </>
          )}
          <button
            type="button"
            aria-label={`Remove condition ${i + 1}`}
            onClick={() => onChange(lines.filter((_, j) => j !== i))}
            className="ml-auto grid h-8 w-8 place-items-center rounded text-mist hover:bg-ash hover:text-parchment"
          >
            ×
          </button>
        </div>
      ))}
      <div>
        <Button type="button" variant="secondary" className="min-h-8" onClick={() => onChange([...lines, newLine(offered[0]!.value)])}>
          Add a condition
        </Button>
      </div>
      {problem && <p className="text-sm text-blood-bright">{problem}</p>}
    </fieldset>
  );
}

function PreviewRow({ label, pricing, ratings, strong }: { label: string; pricing: Pricing; ratings: number[]; strong?: boolean }) {
  return (
    <tr className={strong ? "text-parchment" : "text-mist"}>
      <td className="pr-4">{label}</td>
      {ratings.map((r) => {
        const total = priceAt(pricing, r);
        return (
          <td key={r} className="px-2 text-right tabular-nums">
            {total === null ? "—" : `${total}`}
          </td>
        );
      })}
    </tr>
  );
}
