import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { KeywordIn, KeywordsOut, TroupeKeywordOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { keywordFields, keywordKinds, moved } from "./keywordRules";

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

/**
 * The troupe's downtime keywords (#509), as house rules: what kind of action an answer
 * is, which players choose first. Storytellers rename, reword, reorder, add or retire
 * them, and set each one's fields, the actions it is spent from, its cost, who must take
 * it each cycle and where it comes in the resolution order. Retired keywords stay on
 * past downtimes. Assistant storytellers read them.
 */
export function KeywordsSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const key = ["keywords", troupeId];
  const client = useQueryClient();
  const toast = useToast();
  const listed = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/keywords", { params: { path: { troupe_id: troupeId } } })),
  });
  const [editing, setEditing] = useState<TroupeKeywordOut | "new" | null>(null);
  const [resetting, setResetting] = useState(false);
  const done = (found: KeywordsOut) => client.setQueryData(key, found);
  const path = { params: { path: { troupe_id: troupeId } } };
  const reorder = useAction(async (keys: string[]) => done(await unwrap(api.PUT("/api/troupes/{troupe_id}/keyword-order", { ...path, body: { keys } }))));
  const retire = useAction(async ({ k, retired }: { k: TroupeKeywordOut; retired: boolean }) => {
    done(
      await unwrap(api.PUT("/api/troupes/{troupe_id}/keywords/{key}/retired", { params: { path: { troupe_id: troupeId, key: k.key } }, body: { retired } })),
    );
    toast({ message: retired ? `${k.name} is retired. Past downtimes keep it.` : `${k.name} is offered again.` });
  });
  const reset = useAction(async () => {
    done(await unwrap(api.DELETE("/api/troupes/{troupe_id}/keywords", path)));
    setResetting(false);
  });

  if (listed.isPending) return <Loading />;
  if (listed.error) return <ErrorText error={listed.error} />;
  const data = listed.data;
  const keys = data.keywords.map((k) => k.key);

  return (
    <Card title="Downtime keywords">
      <p className="mb-3 text-sm text-mist">
        A player answering a downtime action first chooses its keyword: what kind of action it is. The keyword decides what the form asks for, which actions it
        can be spent from, what it costs, and where staff resolve it. Feed actions are the character's feeding actions, Patrol its patrols, Learn stands for
        what it is learning, and Observe and Cancel are the Computer skill's. Old answers, with no keyword, count as Narrative.{" "}
        <Link to={manualLink("running-a-troupe", "downtime-keywords")} className="underline hover:text-parchment">
          More in the manual
        </Link>
      </p>
      {canEdit && (
        <div className="mb-3 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setEditing("new")}>
            Add a keyword
          </Button>
          <Button variant="ghost" onClick={() => setResetting(true)}>
            Back to Horatio's keywords…
          </Button>
        </div>
      )}
      <table aria-label="Downtime keywords" className="w-full text-sm">
        {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
        <thead className="max-lg:sr-only">
          <tr className="border-b border-ash text-left text-xs text-mist">
            <th className="py-2 pr-3 font-normal">Keyword</th>
            <th className={`${WIDE} py-2 pr-3 font-normal`}>Asks for</th>
            <th className={`${WIDE} py-2 pr-3 font-normal`}>Spent from</th>
            <th className={`${WIDE} py-2 pr-3 font-normal`}>Step</th>
            <th className="py-2 font-normal">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ash">
          {data.keywords.map((k, i) => {
            const asks = keywordFields(k, data);
            const kinds = keywordKinds(k, data);
            return (
              <tr key={k.key} className={k.retired ? "text-mist" : undefined}>
                <td className="py-2.5 pr-3 align-top">
                  <span className="flex flex-wrap items-center gap-2">
                    <strong className={k.retired ? "font-normal" : "text-parchment"}>{k.name}</strong>
                    {k.retired && <Badge>Retired</Badge>}
                    {k.default && <Badge tone="gold">Changed from {k.default.name}</Badge>}
                    {!k.effect && <Badge tone="gold">Our own</Badge>}
                    {k.cost !== 1 && <span className="text-xs text-mist">costs {k.cost}</span>}
                    {!!k.required_for?.length && <span className="text-xs text-gold">{k.required_for.join(", ")}s take it each cycle</span>}
                  </span>
                  {k.explanation && <span className="mt-0.5 block text-xs text-mist">{k.explanation}</span>}
                  <span className="mt-0.5 block text-xs text-mist lg:hidden">
                    {asks && `Asks for ${asks.toLowerCase()} · `}
                    {kinds} · step {k.step}
                  </span>
                </td>
                <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{asks || "The description only"}</td>
                <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>
                  {kinds}
                  {k.science && <span className="block text-xs">Fits a Science</span>}
                </td>
                <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`} title={data.steps.find((s) => s.step === k.step)?.name}>
                  {k.step}
                </td>
                <td className="w-px py-1 text-right align-top">
                  {canEdit && (
                    <ActionMenu label={`Actions for ${k.name}`} variant="ghost">
                      <MenuGroup label="Change">
                        <MenuItem onSelect={() => setEditing(k)}>Edit…</MenuItem>
                        <MenuItem disabled={i === 0 || reorder.isPending} onSelect={() => reorder.mutate(moved(keys, i, -1))}>
                          Move up
                        </MenuItem>
                        <MenuItem disabled={i === keys.length - 1 || reorder.isPending} onSelect={() => reorder.mutate(moved(keys, i, 1))}>
                          Move down
                        </MenuItem>
                      </MenuGroup>
                      <MenuGroup label="Retire">
                        <MenuItem onSelect={() => retire.mutate({ k, retired: !k.retired })}>{k.retired ? "Offer it again" : "Retire"}</MenuItem>
                      </MenuGroup>
                    </ActionMenu>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <ErrorText error={reorder.error ?? retire.error} />
      <section className="mt-4 text-sm" aria-label="The resolution order">
        <h3 className="mb-1 text-xs tracking-wide text-mist uppercase">The resolution order</h3>
        <ol className="list-decimal pl-5 text-mist">
          {data.steps.map((s) => (
            <li key={s.step}>{s.name}</li>
          ))}
        </ol>
        <p className="mt-1 text-xs text-mist">Within a step, actions come in the order of the keywords above, and influence actions highest first.</p>
      </section>
      <Dialog title={editing === "new" ? "Add a keyword" : editing ? `Edit ${editing.name}` : ""} open={!!editing} onClose={() => setEditing(null)}>
        {editing && (
          <KeywordForm
            key={editing === "new" ? "new" : editing.key}
            troupeId={troupeId}
            data={data}
            keyword={editing === "new" ? null : editing}
            onDone={(found) => {
              done(found);
              setEditing(null);
            }}
          />
        )}
      </Dialog>
      <Dialog title="Back to Horatio's keywords" open={resetting} onClose={() => setResetting(false)}>
        <div className="flex flex-col gap-3 text-sm">
          <p>Every keyword goes back as Horatio has it, in its order. Your own are retired, so past downtimes keep them.</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => reset.mutate(undefined)} disabled={reset.isPending}>
              Go back to Horatio's
            </Button>
            <Button variant="ghost" onClick={() => setResetting(false)}>
              Keep ours
            </Button>
          </div>
          <ErrorText error={reset.error} />
        </div>
      </Dialog>
    </Card>
  );
}

const BLANK: KeywordIn = {
  name: "",
  explanation: "",
  fields: [],
  action_kinds: ["general"],
  computers_only: false,
  science: false,
  cost: 1,
  required_for: [],
  step: 5,
};

/** One keyword's name, wording and rules, to add or change. */
function KeywordForm({
  troupeId,
  data,
  keyword,
  onDone,
}: {
  troupeId: string;
  data: KeywordsOut;
  keyword: TroupeKeywordOut | null;
  onDone: (found: KeywordsOut) => void;
}) {
  const [draft, setDraft] = useState<KeywordIn>(keyword ? { ...BLANK, ...keyword } : BLANK);
  const set = (change: Partial<KeywordIn>) => setDraft({ ...draft, ...change });
  const toggle = (list: string[], value: string, on: boolean) => (on ? [...list, value] : list.filter((v) => v !== value));
  const save = useAction(async () => {
    const body: KeywordIn = {
      name: draft.name,
      explanation: draft.explanation,
      fields: draft.fields,
      action_kinds: draft.action_kinds,
      computers_only: draft.computers_only,
      science: draft.science,
      cost: draft.cost,
      required_for: draft.required_for,
      step: draft.step,
    };
    onDone(
      keyword
        ? await unwrap(api.PUT("/api/troupes/{troupe_id}/keywords/{key}", { params: { path: { troupe_id: troupeId, key: keyword.key } }, body }))
        : await unwrap(api.POST("/api/troupes/{troupe_id}/keywords", { params: { path: { troupe_id: troupeId } }, body })),
    );
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {keyword?.effect && (
        <p className="text-sm text-mist">
          Renamed or reworded, it keeps what follows from {keyword.default?.name ?? keyword.name}, such as feeding or learning.
        </p>
      )}
      <Field label="Name">
        <Input required maxLength={60} value={draft.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="What it is for" hint="One line, shown on the form.">
        <Input maxLength={300} value={draft.explanation ?? ""} onChange={(e) => set({ explanation: e.target.value })} />
      </Field>
      <fieldset className="flex flex-col gap-1 text-sm">
        <legend className="mb-1 text-mist">It asks for, besides the description</legend>
        {data.fields.map((f) => (
          <label key={f.key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={(draft.fields ?? []).includes(f.key)}
              onChange={(e) => set({ fields: toggle(draft.fields ?? [], f.key, e.target.checked) })}
            />
            {f.label}
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-1 text-sm">
        <legend className="mb-1 text-mist">Spent from</legend>
        {Object.entries(data.action_kinds).map(([k, name]) => (
          <label key={k} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={(draft.action_kinds ?? []).includes(k)}
              onChange={(e) => set({ action_kinds: toggle(draft.action_kinds ?? [], k, e.target.checked) })}
            />
            {name}
          </label>
        ))}
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!draft.computers_only} onChange={(e) => set({ computers_only: e.target.checked })} />
          Only the Computer skill's action, once a cycle
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!draft.science} onChange={(e) => set({ science: e.target.checked })} />
          Fits a Science, so a Science's action can go on it
        </label>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Actions it costs">
          <Input type="number" min={0} max={5} value={draft.cost ?? 1} onChange={(e) => set({ cost: Math.max(0, Math.min(5, Number(e.target.value) || 0)) })} />
        </Field>
        <Field label="Step of the resolution order">
          <Select value={draft.step ?? 5} onChange={(e) => set({ step: Number(e.target.value) })}>
            {data.steps.map((s) => (
              <option key={s.step} value={s.step}>
                {s.step}. {s.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <legend className="mb-1 text-mist">Required each cycle of</legend>
        {data.ages.map((age) => (
          <label key={age} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={(draft.required_for ?? []).includes(age)}
              onChange={(e) => set({ required_for: toggle(draft.required_for ?? [], age, e.target.checked) })}
            />
            {age}s
          </label>
        ))}
      </fieldset>
      <ErrorText error={save.error} />
      <Button type="submit" className="self-start" disabled={save.isPending || !draft.name.trim()}>
        {keyword ? "Save keyword" : "Add keyword"}
      </Button>
    </form>
  );
}
