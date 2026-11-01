import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CostCategoryOut, CostOut, CostsOut } from "../../api/types";
import { Explainer } from "../../components/Explainer";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { pageText } from "./bookPage";
import { useHouseSplat } from "./HouseSplat";
import { flat, overlaps, parseTable, previewRatings, priceAt, SCHEMES } from "./costs";
import type { Pricing, Scheme } from "./costs";

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
  const costs = useQuery({
    queryKey: ["costs", troupeId, splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/costs", { params: { path: { troupe_id: troupeId }, query: { splat } } })),
  });
  const remove = useAction((id: string) =>
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
      (!q || `${categories.get(c.category)?.name} ${subject(c, categories.get(c.category))}`.toLowerCase().includes(q)),
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
                        <span className={c.replaced ? "" : "text-parchment"}>{subject(c, category)}</span>
                        {": "}
                        <span>{c.price_text}</span>
                        {c.page && <span className="text-mist"> {pageText(c.page)}</span>}
                        {c.text && <span className="block text-xs text-mist no-underline">House rule: {c.text}</span>}
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {c.house && <Badge tone="gold">House rule</Badge>}
                        {c.replaced && <Badge>replaced here</Badge>}
                        {canEdit && c.house && c.id && (
                          <>
                            <Button variant="ghost" className="min-h-8 px-2" onClick={() => setEditing({ kind: "change", cost: c })}>
                              Change
                            </Button>
                            <Button
                              variant="ghost"
                              className="min-h-8 px-2"
                              aria-label={`Remove the price for ${subject(c, category)}`}
                              onClick={() => remove.mutate(c.id!)}
                            >
                              Remove
                            </Button>
                          </>
                        )}
                        {canEdit && !c.house && !c.replaced && (c.trait !== null || !category?.per_trait) && (
                          <Button
                            variant="ghost"
                            className="min-h-8 px-2"
                            aria-label={`Change the price for ${subject(c, category)}`}
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
  const [category, setCategory] = useState(start?.category ?? data.categories[0]?.key ?? "");
  const [trait, setTrait] = useState(start?.trait ?? "");
  const [scheme, setScheme] = useState<Scheme>(start?.scheme ?? "per_dot");
  const [rate, setRate] = useState(start?.rate?.toString() ?? "");
  const [table, setTable] = useState(start?.table?.join(", ") ?? "");
  const [text, setText] = useState(editing.kind === "change" ? (editing.cost.text ?? "") : "");
  const cat = data.categories.find((c) => c.key === category);
  const catalogue = useQuery({
    // The rule set's own catalogue, for the book ratings of merits and flaws.
    queryKey: ["catalogue", splat, null],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: {} } })),
    enabled: editing.kind === "new",
  });
  const traits = (catalogue.data?.traits ?? []).filter((t) => t.category === category).map((t) => t.name);
  // A merit or flaw held at one rating, by the book: a fixed price here is its value.
  const bookRating =
    start?.fixed_rating ?? catalogue.data?.traits.find((t) => t.category === category && t.name === trait)?.fixed_rating ?? null;

  const pricing: Pricing = {
    scheme,
    rate: rate.trim() === "" ? null : Number(rate),
    table: scheme === "table" ? parseTable(table) : null,
  };
  const body = { scheme, rate: pricing.rate, table: pricing.table, text };
  const save = useAction(async () => {
    if (editing.kind === "change") {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/costs/{cost_id}", {
          params: { path: { troupe_id: troupeId, cost_id: editing.cost.id! }, query: { splat } },
          body,
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/costs", {
          params: { path: { troupe_id: troupeId }, query: { splat } },
          body: { ...body, category, trait: trait || null, condition: start?.condition ?? null },
        }),
      );
    }
    onClose();
  });

  const target = { category, trait: trait || null, condition: start?.condition ?? null };
  const { replaces, stillApplies } = overlaps(target, data.costs);
  const ratings = flat(pricing) ? [1] : previewRatings(cat?.max_rating ?? null);
  const needsRate = scheme === "per_dot" || scheme === "progressive" || scheme === "fixed";
  const ready =
    !!category && (!cat?.per_trait || !!trait) && (!needsRate || pricing.rate !== null) && (scheme !== "table" || pricing.table !== null);
  const unit = cat?.unit ?? "dot";
  const title =
    editing.kind === "new" ? "Add a price" : `Price for ${subject(editing.cost, cat)}`;

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
            {stillApplies.map((c) => `${subject(c, cat)} (${c.price_text})`).join("; ")}.
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
