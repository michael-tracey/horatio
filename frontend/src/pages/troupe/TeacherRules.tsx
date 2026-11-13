import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TeacherRuleIn, TeacherRuleOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { RowEditor, useRowEditor } from "../../components/RowEditor";
import { Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { TraitList } from "./HouseEffects";
import { Blocks } from "./OwnChecks";
import { namesIn } from "./ownChecks";
import { EMPTY, EXAMPLES, draftOf, teachable, toBody, topOf, type Draft, type WhichHow } from "./teacherRules";
import { useCatalogue } from "../../catalogue";

function numbers(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}

const sameRule = (a: TeacherRuleOut | "new", b: TeacherRuleOut | "new") => (a === "new" || b === "new" ? a === b : a.id === b.id);

/**
 * The troupe's teacher rules, in the Settings at the top of Characters › Approvals (#785): kinds of trait that
 * need a teacher here beyond discipline dots. None by default, and then nothing
 * changes. Storytellers add one, change it or remove it; each change goes in the
 * troupe's log, and the players' House rules tab lists them.
 */
export function TeacherRules({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const editor = useRowEditor<TeacherRuleOut | "new">(sameRule);
  const editing = editor.open;
  const [removing, setRemoving] = useState<TeacherRuleOut | null>(null);
  const list = useQuery({
    queryKey: ["teacher-rules", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/teacher-rules", { params: { path: { troupe_id: troupeId } } })),
  });
  const remove = useAction((id: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/teacher-rules/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: id } } })),
  );

  return (
    <Card
      title="Teachers"
      actions={
        canEdit &&
        !editing && (
          <Button variant="secondary" ref={editor.fallback} onClick={(e) => editor.toggle("new", e.currentTarget)}>
            Add a rule
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Discipline dots need a teacher by the book. Rules here ask one for other traits too. A player buying a matching trait picks a teacher from the
        troupe's characters who qualify, or names an NPC for you to approve, and the purchase waits on the Approvals tab.
      </p>
      {editing === "new" && (
        <RowEditor className="mb-4">
          <TeacherRuleEditor troupeId={troupeId} editing="new" onClose={editor.close} />
        </RowEditor>
      )}
      {list.isPending && <Loading />}
      <ErrorText error={list.error} />
      {list.data?.length === 0 && editing !== "new" && (
        <EmptyState title="No teacher rules.">{canEdit ? "Only discipline dots need a teacher. Add a rule to ask one for more." : "Only discipline dots need a teacher."}</EmptyState>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="divide-y divide-ash" aria-label="Teacher rules">
          {list.data.map((r) => (
            <li key={r.id} className="flex flex-col gap-1 py-2.5">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="min-w-48 flex-1 text-sm text-parchment">{r.text}</span>
                {canEdit && (
                  <span className="flex shrink-0 flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      className="min-h-8 px-3"
                      aria-label={`Change: ${r.text}`}
                      aria-expanded={editor.isOpen(r)}
                      onClick={(e) => editor.toggle(r, e.currentTarget)}
                    >
                      Change
                    </Button>
                    <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove: ${r.text}`} onClick={() => setRemoving(r)}>
                      Remove
                    </Button>
                  </span>
                )}
              </div>
              {r.problem && <p className="text-xs text-blood-bright">Not applied: {r.problem}</p>}
              {editor.isOpen(r) && (
                <RowEditor className="pt-2">
                  <TeacherRuleEditor troupeId={troupeId} editing={r} onClose={editor.close} />
                </RowEditor>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialog title="Remove this rule?" open={removing !== null} onClose={() => setRemoving(null)}>
        <p className="text-sm">{removing?.text}</p>
        <p className="mt-2 text-sm text-mist">It stops applying at once. Purchases already waiting keep their teacher.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            onClick={() => {
              if (removing) remove.mutate(removing.id, { onSuccess: () => setRemoving(null) });
            }}
          >
            Remove it
          </Button>
          <Button variant="ghost" onClick={() => setRemoving(null)}>
            Keep it
          </Button>
        </div>
        <ErrorText error={remove.error} />
      </Dialog>
    </Card>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

function usePreview(troupeId: string, body: TeacherRuleIn | null) {
  const settled = useDebounced(body, 300);
  return useQuery({
    queryKey: ["teacher-rule-preview", troupeId, settled],
    queryFn: () => unwrap(api.POST("/api/troupes/{troupe_id}/teacher-rules/preview", { params: { path: { troupe_id: troupeId } }, body: settled! })),
    enabled: settled !== null,
    placeholderData: keepPreviousData,
  });
}

const WHICH: { how: WhichHow; label: string }[] = [
  { how: "traits", label: "These traits" },
  { how: "prefix", label: "Names starting with…" },
  { how: "all", label: "All of them" },
];

function TeacherRuleEditor({ troupeId, editing, onClose }: { troupeId: string; editing: TeacherRuleOut | "new"; onClose: () => void }) {
  const unreadable = editing !== "new" && draftOf(editing) === null;
  const [draft, setDraft] = useState<Draft>(editing === "new" ? EMPTY : (draftOf(editing) ?? EMPTY));
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const catalogue = useCatalogue(draft.splat, troupeId);
  const built = toBody(draft);
  const body = "body" in built ? built.body : null;
  const preview = usePreview(troupeId, body);
  const save = useAction(async () => {
    if (!body) return;
    if (editing === "new") await unwrap(api.POST("/api/troupes/{troupe_id}/teacher-rules", { params: { path: { troupe_id: troupeId } }, body }));
    else await unwrap(api.PUT("/api/troupes/{troupe_id}/teacher-rules/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: editing.id } }, body }));
    onClose();
  });
  const splats = ["vampire", ...(troupe.data?.allowed_splats ?? []).filter((s) => s !== "vampire")];
  const cat = catalogue.data;
  const problem = "problem" in built ? built.problem : preview.data?.problem;
  const text = body ? preview.data?.text : "";
  const title = editing === "new" ? "A new teacher rule" : "Change the teacher rule";

  return (
    <section aria-label={title} className="flex flex-col gap-4 rounded-md border border-gold/40 p-3 sm:p-4">
      <h3 className="text-gold">{title}</h3>
      {unreadable && <p className="text-sm text-blood-bright">The form cannot show this rule's condition. Build it again, or keep it as it is.</p>}
      {!cat && <Loading />}
      <ErrorText error={catalogue.error} />
      {cat && (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          {editing === "new" && (
            <Field label="Start from an example (optional)">
              <Select
                value=""
                onChange={(e) => {
                  const found = EXAMPLES.find((x) => x.label === e.target.value);
                  if (found) setDraft({ ...found.draft, splat: draft.splat });
                }}
                className="sm:w-[28rem]"
              >
                <option value="">Choose…</option>
                {EXAMPLES.map((x) => (
                  <option key={x.label}>{x.label}</option>
                ))}
              </Select>
            </Field>
          )}

          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-1 text-sm text-mist">Which traits</legend>
            {splats.length > 1 && (
              <Field label="For">
                <Select value={draft.splat} onChange={(e) => setDraft({ ...draft, splat: e.target.value, names: [], blocks: [] })}>
                  {splats.map((s) => (
                    <option key={s} value={s}>
                      {s[0]!.toUpperCase() + s.slice(1)} characters
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Kind of trait">
              <Select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value, names: [] })}>
                {teachable(cat).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Which">
              <Select value={draft.how} onChange={(e) => set("how", e.target.value as WhichHow)}>
                {WHICH.map((h) => (
                  <option key={h.how} value={h.how}>
                    {h.label}
                  </option>
                ))}
              </Select>
            </Field>
            {draft.how === "traits" && (
              <TraitList name="Rule" label="Traits" options={namesIn(cat, draft.category)} names={draft.names} onChange={(names) => set("names", names)} />
            )}
            {draft.how === "prefix" && (
              <Field label="Names starting with">
                <Input value={draft.prefix} maxLength={200} placeholder="Lore:" onChange={(e) => set("prefix", e.target.value)} />
              </Field>
            )}
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 text-sm text-mist">For whom, and when</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="For whom">
                <Select value={draft.everyone ? "everyone" : "some"} onChange={(e) => set("everyone", e.target.value === "everyone")}>
                  <option value="everyone">Everyone</option>
                  <option value="some">Only characters who…</option>
                </Select>
              </Field>
              <Field label="When">
                <Select value={draft.always ? "always" : "after"} onChange={(e) => set("always", e.target.value === "always")}>
                  <option value="after">After character creation only</option>
                  <option value="always">Always, during creation too</option>
                </Select>
              </Field>
            </div>
            {!draft.everyone && (
              <Blocks
                name="Who"
                legend="Who needs a teacher (every block must hold)"
                blocks={draft.blocks}
                catalogue={cat}
                subject={draft.category}
                onChange={(blocks) => set("blocks", blocks)}
              />
            )}
          </fieldset>

          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-1 text-sm text-mist">The teacher, and what learning takes</legend>
            <Field label="The teacher holds the trait at">
              <Select value={draft.holds} onChange={(e) => set("holds", e.target.value as Draft["holds"])}>
                <option value="same">The rating being bought, or more</option>
                <option value="rating">A set rating, or more</option>
              </Select>
            </Field>
            {draft.holds === "rating" && (
              <Field label="Rating">
                <Select value={draft.rating} onChange={(e) => set("rating", Number(e.target.value))}>
                  {numbers(1, topOf(cat, draft.category)).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Downtime actions to learn">
              <Select value={draft.actions} onChange={(e) => set("actions", Number(e.target.value))}>
                {numbers(0, 5).map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? "None" : n}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="The teacher's Willpower">
              <Select value={draft.willpower} onChange={(e) => set("willpower", Number(e.target.value))}>
                {numbers(0, 5).map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? "None" : n}
                  </option>
                ))}
              </Select>
            </Field>
            {draft.willpower > 0 && (
              <Field label="Games until it returns" hint="Games the teacher attends after spending it.">
                <Select value={draft.games} onChange={(e) => set("games", Number(e.target.value))}>
                  {numbers(1, 12).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </fieldset>

          <section aria-label="Preview" className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/5 p-3 text-sm">
            <h4 className="text-gold">In plain words</h4>
            {problem && <p className="text-blood-bright">{problem}</p>}
            {!problem && text && <p className="text-parchment">{text}</p>}
            <ErrorText error={preview.error} />
          </section>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!body || !!problem || save.isPending}>
              {editing === "new" ? "Add the rule" : "Save"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      )}
    </section>
  );
}
