import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { AllowanceOut, AllowancesOut } from "../../api/types";
import { Explainer } from "../../components/Explainer";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { useHouseSplat } from "./HouseSplat";
import { InfluenceLookback } from "./InfluenceLookback";

/** An editor's target: a new trait rule, a rule set rule to replace, or a troupe rule to change. */
type Editing = { kind: "new" } | { kind: "replace"; rule: AllowanceOut } | { kind: "change"; rule: AllowanceOut };

/**
 * How many downtime actions of each kind characters get each cycle, and what
 * traits add or take away. A cycle keeps the allowances it was opened with.
 */
export function AllowancesSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const { splat, picker } = useHouseSplat(troupeId);
  const allowances = useQuery({
    queryKey: ["allowances", troupeId, splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/allowances", { params: { path: { troupe_id: troupeId }, query: { splat } } })),
  });
  const remove = useAction((id: string) =>
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

      {editing && (
        <AllowanceEditor key={JSON.stringify(editing)} troupeId={troupeId} splat={splat} data={allowances.data} editing={editing} onClose={() => setEditing(null)} />
      )}

      <Card
        title="Downtime actions"
        actions={
          canEdit &&
          !editing && (
            <Button variant="secondary" onClick={() => setEditing({ kind: "new" })}>
              Add a trait
            </Button>
          )
        }
      >
        <div className="flex flex-col gap-5">
          {[...groups].map(([kind, rules]) => (
            <section key={kind}>
              <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{kindName(kind)}</h3>
              <ul className="divide-y divide-ash">
                {rules.map((r) => (
                  <li key={r.id ?? `${r.category}-${r.trait}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                    <span className={`min-w-48 flex-1 text-sm ${r.replaced ? "text-mist line-through" : ""}`}>
                      <span className={r.replaced ? "" : "text-parchment"}>{r.who}</span>: {r.amount_text}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      {r.house && <Badge tone="gold">House rule</Badge>}
                      {r.replaced && <Badge>replaced here</Badge>}
                      {canEdit && r.house && r.id && (
                        <>
                          <Button variant="ghost" className="min-h-8 px-2" aria-label={`Change actions for ${r.who}`} onClick={() => setEditing({ kind: "change", rule: r })}>
                            Change
                          </Button>
                          <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove actions for ${r.who}`} onClick={() => remove.mutate(r.id!)}>
                            Remove
                          </Button>
                        </>
                      )}
                      {canEdit && !r.house && !r.replaced && (
                        <Button variant="ghost" className="min-h-8 px-2" aria-label={`Change actions for ${r.who}`} onClick={() => setEditing({ kind: "replace", rule: r })}>
                          Change
                        </Button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <ErrorText error={remove.error} />
      </Card>
      <InfluenceLookback troupeId={troupeId} canEdit={canEdit} />
    </div>
  );
}

function AllowanceEditor({ troupeId, splat, data, editing, onClose }: { troupeId: string; splat: string; data: AllowancesOut; editing: Editing; onClose: () => void }) {
  const start = editing.kind === "new" ? null : editing.rule;
  const [actionKind, setActionKind] = useState(start?.action_kind ?? data.action_kinds[0]?.key ?? "general");
  const [category, setCategory] = useState(start?.category ?? "flaws");
  const [trait, setTrait] = useState(start?.trait ?? "");
  const [scheme, setScheme] = useState<"fixed" | "per_dot">(start?.scheme ?? "fixed");
  const [amount, setAmount] = useState(start?.amount.toString() ?? "-1");
  const [minRating, setMinRating] = useState(start?.min_rating.toString() ?? "1");
  const catalogue = useQuery({
    queryKey: ["catalogue", splat, null],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: {} } })),
    enabled: editing.kind === "new",
  });
  const categories = (catalogue.data?.categories ?? []).filter((c) => c.rated && !c.derived);
  const traits = (catalogue.data?.traits ?? []).filter((t) => t.category === category).map((t) => t.name);
  const everyone = start !== null && start.trait === null;

  const body = { scheme, amount: Number(amount), min_rating: Number(minRating) };
  const save = useAction(async () => {
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
  const ready = amount.trim() !== "" && !Number.isNaN(Number(amount)) && (everyone || !!trait);
  const kindName = data.action_kinds.find((k) => k.key === actionKind)?.name ?? actionKind;

  return (
    <Card title={start ? `Actions for ${start.who}` : "Add a trait that changes the allowance"}>
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
                <Select value={scheme} onChange={(e) => setScheme(e.target.value as "fixed" | "per_dot")}>
                  <option value="fixed">Once, at any rating</option>
                  <option value="per_dot">For each dot</option>
                </Select>
              </Field>
              <Field label="From rating">
                <Input type="number" min={1} value={minRating} onChange={(e) => setMinRating(e.target.value)} />
              </Field>
            </>
          )}
        </div>
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
    </Card>
  );
}
