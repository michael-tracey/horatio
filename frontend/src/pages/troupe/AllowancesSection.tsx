import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { AllowanceOut, AllowancesOut } from "../../api/types";
import { Explainer } from "../../components/Explainer";
import { RowEditor, useRowEditor } from "../../components/RowEditor";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { useHouseSplat } from "./HouseSplat";
import { InfluenceLookback } from "./InfluenceLookback";
import { RareDisciplinesSetting } from "./RareDisciplinesSetting";
import { useCatalogue } from "../../catalogue";

type Scheme = AllowanceOut["scheme"];

/** "1, 3, 5": the rating each further field needs, from what staff typed; null if it doesn't read. */
export function fieldRatings(text: string): number[] | null {
  const ratings = text.split(/[\s,]+/).filter(Boolean).map(Number);
  return ratings.every((r) => Number.isInteger(r) && r >= 1) ? ratings : null;
}

/** An editor's target: a new trait rule, a rule set rule to replace, or a troupe rule to change. */
type Editing = { kind: "new" } | { kind: "replace"; rule: AllowanceOut } | { kind: "change"; rule: AllowanceOut };
const sameEditing = (a: Editing, b: Editing) => JSON.stringify(a) === JSON.stringify(b);

/**
 * How many downtime actions of each kind characters get each cycle, and what
 * traits add or take away. A cycle keeps the allowances it was opened with.
 */
export function AllowancesSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const editor = useRowEditor<Editing>(sameEditing);
  const editing = editor.open;
  const { splat, picker } = useHouseSplat(troupeId);
  const allowances = useQuery({
    queryKey: ["allowances", troupeId, splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/allowances", { params: { path: { troupe_id: troupeId }, query: { splat } } })),
  });
  const remove = useRulesAction((id: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/allowances/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: id }, query: { splat } } })),
  );
  if (allowances.isPending) return <Loading />;
  if (allowances.error) return <ErrorText error={allowances.error} />;

  const groups = new Map<string, AllowanceOut[]>();
  for (const r of allowances.data.rules) groups.set(r.action_kind, [...(groups.get(r.action_kind) ?? []), r]);
  const kindName = (key: string) => allowances.data.action_kinds.find((k) => k.key === key)?.name ?? key;

  return (
    <div className="flex flex-col gap-6">
      {picker}
      <Explainer id="rules-actions" title="How downtime actions work">
        <p className="text-sm">
          Each cycle, a character gets the base number of actions of each kind, and each trait below adds or takes away
          actions while the character holds it. A rule of this troupe's for the same thing replaces the rule set's.
        </p>
        <p className="mt-2 text-sm text-mist">
          A change applies to cycles opened after it. A cycle already open keeps the allowances it opened with; adjust one
          character's actions on the cycle's Participants page.
        </p>
      </Explainer>

      <Card
        title="Downtime actions"
        actions={
          canEdit &&
          !editing && (
            <Button variant="secondary" ref={editor.fallback} onClick={(e) => editor.toggle({ kind: "new" }, e.currentTarget)}>
              Add a trait
            </Button>
          )
        }
      >
        {editing?.kind === "new" && (
          <RowEditor className="mb-4">
            <AllowanceEditor troupeId={troupeId} splat={splat} data={allowances.data} editing={editing} onClose={editor.close} />
          </RowEditor>
        )}
        <div className="flex flex-col gap-5">
          {[...groups].map(([kind, rules]) => (
            <section key={kind}>
              <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{kindName(kind)}</h3>
              <ul className="divide-y divide-ash">
                {rules.map((r) => {
                  const change: Editing = r.house ? { kind: "change", rule: r } : { kind: "replace", rule: r };
                  const open = editor.isOpen(change);
                  return (
                    <li key={r.id ?? `${r.category}-${r.trait}`}>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                        <span className={`min-w-48 flex-1 text-sm ${r.replaced ? "text-mist line-through" : ""}`}>
                          <span className={r.replaced ? "" : "text-parchment"}>{r.who}</span>: {r.amount_text}
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          {r.house && <Badge tone="gold">House rule</Badge>}
                          {r.replaced && <Badge>Replaced here</Badge>}
                          {canEdit && r.house && r.id && (
                            <>
                              <Button
                                variant="secondary"
                                className="min-h-8 px-3"
                                aria-label={`Change actions for ${r.who}`}
                                aria-expanded={open}
                                onClick={(e) => editor.toggle(change, e.currentTarget)}
                              >
                                Change
                              </Button>
                              <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove actions for ${r.who}`} onClick={() => remove.mutate(r.id!)}>
                                Remove
                              </Button>
                            </>
                          )}
                          {canEdit && !r.house && !r.replaced && (
                            <Button
                              variant="secondary"
                              className="min-h-8 px-3"
                              aria-label={`Change actions for ${r.who}`}
                              aria-expanded={open}
                              onClick={(e) => editor.toggle(change, e.currentTarget)}
                            >
                              Change
                            </Button>
                          )}
                        </span>
                      </div>
                      {open && (
                        <RowEditor className="pb-3">
                          <AllowanceEditor troupeId={troupeId} splat={splat} data={allowances.data} editing={change} onClose={editor.close} />
                        </RowEditor>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
        <ErrorText error={remove.error} />
      </Card>
      <RareDisciplinesSetting troupeId={troupeId} canEdit={canEdit} />
      <InfluenceLookback troupeId={troupeId} canEdit={canEdit} />
    </div>
  );
}

function AllowanceEditor({ troupeId, splat, data, editing, onClose }: { troupeId: string; splat: string; data: AllowancesOut; editing: Editing; onClose: () => void }) {
  const start = editing.kind === "new" ? null : editing.rule;
  const [actionKind, setActionKind] = useState(start?.action_kind ?? data.action_kinds[0]?.key ?? "general");
  const [category, setCategory] = useState(start?.category ?? "flaws");
  const [trait, setTrait] = useState(start?.trait ?? "");
  const [scheme, setScheme] = useState<Scheme>(start?.scheme ?? "fixed");
  const [ratings, setRatings] = useState((start?.detail_ratings ?? []).join(", "));
  const [amount, setAmount] = useState(start?.amount.toString() ?? "-1");
  const [minRating, setMinRating] = useState(start?.min_rating.toString() ?? "1");
  // The rule set as written: an allowance is set against the book.
  const catalogue = useCatalogue(splat, null, { enabled: editing.kind === "new" });
  const categories = (catalogue.data?.categories ?? []).filter((c) => c.rated && !c.derived);
  const traits = (catalogue.data?.traits ?? []).filter((t) => t.category === category).map((t) => t.name);
  const everyone = start !== null && start.trait === null;

  const detailRatings = scheme === "per_detail" ? fieldRatings(ratings) : [];
  const body = { scheme, amount: Number(amount), min_rating: Number(minRating), detail_ratings: detailRatings ?? [] };
  const save = useRulesAction(async () => {
    if (editing.kind === "change") {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/allowances/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: editing.rule.id! }, query: { splat } }, body }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/allowances", {
          params: { path: { troupe_id: troupeId }, query: { splat } },
          body: { ...body, action_kind: actionKind, category: everyone ? null : category, trait: everyone ? null : trait },
        }),
      );
    }
    onClose();
  });
  const ready = amount.trim() !== "" && !Number.isNaN(Number(amount)) && (everyone || !!trait) && detailRatings !== null;
  const kindName = data.action_kinds.find((k) => k.key === actionKind)?.name ?? actionKind;
  const title = start ? `Actions for ${start.who}` : "Add a trait that changes the allowance";

  return (
    <section aria-label={title} className="flex flex-col gap-3 rounded-md border border-gold/40 p-3 sm:p-4">
      <h3 className="text-gold">{title}</h3>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        {editing.kind === "new" && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Action kind">
              <Select value={actionKind} onChange={(e) => setActionKind(e.target.value)}>
                {data.action_kinds.map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Category">
              <Select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setTrait("");
                }}
              >
                {categories.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Trait">
              <Input list="allowance-traits" value={trait} onChange={(e) => setTrait(e.target.value)} placeholder="Search…" />
            </Field>
            <datalist id="allowance-traits">
              {traits.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={everyone ? `${kindName}s each cycle` : "Actions"} hint={everyone ? undefined : "Negative to take actions away."}>
            <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          {!everyone && (
            <>
              <Field label="How it counts">
                <Select value={scheme} onChange={(e) => setScheme(e.target.value as Scheme)}>
                  <option value="fixed">Once, at any rating</option>
                  <option value="per_dot">For each dot</option>
                  <option value="per_detail">For each field held</option>
                </Select>
              </Field>
              <Field label="From rating">
                <Input type="number" min={1} value={minRating} onChange={(e) => setMinRating(e.target.value)} />
              </Field>
            </>
          )}
        </div>
        {!everyone && scheme === "per_detail" && (
          <Field
            label="Rating each field needs"
            hint="Empty: one for every field, as the book has Science. 1, 3, 5: the first field at 1 dot, a second at 3 and a third at 5, counting the character's best."
          >
            <Input value={ratings} onChange={(e) => setRatings(e.target.value)} placeholder="1, 3, 5" />
          </Field>
        )}
        <ErrorText error={save.error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={!ready || save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
