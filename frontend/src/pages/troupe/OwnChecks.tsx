import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, OwnCheckIn, OwnCheckOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { TraitList } from "./HouseEffects";
import {
  COND_TYPES,
  EMPTY,
  STRENGTHS,
  clans,
  draftOf,
  namesIn,
  newCondBlock,
  strengthLabel,
  subjectCategories,
  toBody,
  topRating,
  typesIn,
  type CondBlock,
  type CondType,
  type Draft,
  type SubjectHow,
} from "./ownChecks";

const TONE: Record<string, "blood" | "gold" | "mist"> = { refuse: "blood", complete: "blood", review: "gold", note: "mist" };

function numbers(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}

function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-36 flex-col gap-1 text-sm">
      <span aria-hidden className="text-mist">
        {label}
      </span>
      {children}
    </div>
  );
}

/**
 * The troupe's own checks, beside the book's on the Checks page: what each says,
 * how strictly it holds, and the characters it flags now. Storytellers add one with
 * the builder, change it or remove it; every change goes in the troupe's log.
 */
export function OwnChecks({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [editing, setEditing] = useState<OwnCheckOut | "new" | null>(null);
  const [removing, setRemoving] = useState<OwnCheckOut | null>(null);
  const list = useQuery({
    queryKey: ["own-checks", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/house-checks", { params: { path: { troupe_id: troupeId } } })),
  });
  const remove = useAction((id: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/house-checks/{check_id}", { params: { path: { troupe_id: troupeId, check_id: id } } })),
  );

  return (
    <Card
      title="The troupe's own checks"
      actions={
        canEdit &&
        !editing && (
          <Button variant="secondary" onClick={() => setEditing("new")}>
            Add a check
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Checks this troupe added beside the book's. Each works as a book check does. A character who breaks one when it is added is flagged on
        their sheet, not changed.
      </p>
      {editing && <OwnCheckEditor key={editing === "new" ? "new" : editing.id} troupeId={troupeId} editing={editing} onClose={() => setEditing(null)} />}
      {list.isPending && <Loading />}
      <ErrorText error={list.error} />
      {list.data?.length === 0 && !editing && (
        <EmptyState title="No checks of the troupe's own yet.">
          {canEdit ? "Add one with Add a check: pick what it is about, then build what it needs from blocks." : "Its storytellers can add them."}
        </EmptyState>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="divide-y divide-ash" aria-label="The troupe's own checks">
          {list.data.map((c) => (
            <li key={c.id} className="flex flex-col gap-1 py-2.5">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="min-w-48 flex-1 text-sm text-parchment">
                  {c.message}
                  <span className="ml-2">
                    <Badge tone="gold">Our own</Badge>
                  </span>
                </span>
                <span className="flex shrink-0 flex-wrap items-center gap-2">
                  <Badge tone={TONE[c.strength]}>{strengthLabel(c.strength)}</Badge>
                  {canEdit && (
                    <>
                      <Button variant="secondary" className="min-h-8 px-3" aria-label={`Change: ${c.message}`} onClick={() => setEditing(c)}>
                        Change
                      </Button>
                      <Button variant="ghost" className="min-h-8 px-2" aria-label={`Remove: ${c.message}`} onClick={() => setRemoving(c)}>
                        Remove
                      </Button>
                    </>
                  )}
                </span>
              </div>
              <p className="text-xs text-mist">{c.text}</p>
              {c.problem && <p className="text-xs text-blood-bright">Not applied: {c.problem}</p>}
              {c.breaking.length > 0 && <p className="text-xs text-gold">Flagged on: {c.breaking.map((b) => b.name).join(", ")}</p>}
            </li>
          ))}
        </ul>
      )}
      <Dialog title="Remove this check?" open={removing !== null} onClose={() => setRemoving(null)}>
        <p className="text-sm">{removing?.message}</p>
        <p className="mt-2 text-sm text-mist">It stops applying at once. Nothing on any sheet changes.</p>
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
  const [shown, setShown] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setShown(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return shown;
}

/** The server's reading of the check as it is built: in words, and whom it would flag. */
function useOwnCheckPreview(troupeId: string, body: OwnCheckIn | null, checkId: string | null) {
  const asked = useDebounced(JSON.stringify({ body, checkId }), 300);
  return useQuery({
    queryKey: ["own-check-preview", troupeId, asked],
    queryFn: () => {
      const { body: check, checkId: id } = JSON.parse(asked) as { body: OwnCheckIn; checkId: string | null };
      return unwrap(
        api.POST("/api/troupes/{troupe_id}/house-checks/preview", {
          params: { path: { troupe_id: troupeId } },
          body: { check, house_check_id: id },
        }),
      );
    },
    enabled: (JSON.parse(asked) as { body: OwnCheckIn | null }).body !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

const HOW: { how: SubjectHow; label: string }[] = [
  { how: "trait", label: "One trait" },
  { how: "prefix", label: "Names starting with…" },
  { how: "kind", label: "One type" },
  { how: "all", label: "All of them" },
];

function OwnCheckEditor({ troupeId, editing, onClose }: { troupeId: string; editing: OwnCheckOut | "new"; onClose: () => void }) {
  const unreadable = editing !== "new" && draftOf(editing) === null;
  const [draft, setDraft] = useState<Draft>(editing === "new" ? EMPTY : (draftOf(editing) ?? { ...EMPTY, message: editing.message }));
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const catalogue = useQuery({
    queryKey: ["catalogue", draft.splat, troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: draft.splat }, query: { troupe_id: troupeId } } })),
  });
  const built = toBody(draft);
  const body = "body" in built ? built.body : null;
  const preview = useOwnCheckPreview(troupeId, body, editing === "new" ? null : editing.id);
  const save = useAction(async () => {
    if (!body) return;
    if (editing === "new") await unwrap(api.POST("/api/troupes/{troupe_id}/house-checks", { params: { path: { troupe_id: troupeId } }, body }));
    else
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/house-checks/{check_id}", {
          params: { path: { troupe_id: troupeId, check_id: editing.id } },
          body,
        }),
      );
    onClose();
  });
  const splats = ["vampire", ...(troupe.data?.allowed_splats ?? []).filter((s) => s !== "vampire")];
  const cat = catalogue.data;
  const problem = "problem" in built ? built.problem : preview.data?.problem;
  const text = body ? preview.data?.text : "";

  return (
    <section aria-label={editing === "new" ? "A new check" : "Change the check"} className="mb-4 flex flex-col gap-4 rounded-md border border-gold/40 p-3 sm:p-4">
      <h3 className="text-gold">{editing === "new" ? "A new check" : "Change the check"}</h3>
      {unreadable && <p className="text-sm text-blood-bright">The form cannot show this check's condition. Build it again, or keep it as it is.</p>}
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
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-1 text-sm text-mist">What it is about</legend>
            {splats.length > 1 && (
              <Field label="For">
                <Select value={draft.splat} onChange={(e) => setDraft({ ...draft, splat: e.target.value, value: "", blocks: [] })}>
                  {splats.map((s) => (
                    <option key={s} value={s}>
                      {s[0]!.toUpperCase() + s.slice(1)} characters
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Kind of trait">
              <Select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value, value: "" })}>
                {subjectCategories(cat).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Which">
              <Select value={draft.how} onChange={(e) => setDraft({ ...draft, how: e.target.value as SubjectHow, value: "" })}>
                {HOW.filter((h) => h.how !== "kind" || typesIn(cat, draft.category).length > 0).map((h) => (
                  <option key={h.how} value={h.how}>
                    {h.label}
                  </option>
                ))}
              </Select>
            </Field>
            {draft.how === "trait" && (
              <Field label="Trait">
                <Select value={draft.value} onChange={(e) => set("value", e.target.value)}>
                  <option value="">Choose…</option>
                  {namesIn(cat, draft.category).map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </Select>
              </Field>
            )}
            {draft.how === "prefix" && (
              <Field label="Names starting with">
                <Input value={draft.value} maxLength={200} placeholder="Bloodline:" onChange={(e) => set("value", e.target.value)} />
              </Field>
            )}
            {draft.how === "kind" && (
              <Field label="Type">
                <Select value={draft.value} onChange={(e) => set("value", e.target.value)}>
                  <option value="">Choose…</option>
                  {typesIn(cat, draft.category).map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </Select>
              </Field>
            )}
          </fieldset>

          <Field label="It">
            <Select value={draft.mode} onChange={(e) => set("mode", e.target.value as Draft["mode"])} className="sm:w-80">
              <option value="forbids">Is not allowed when…</option>
              <option value="requires">Is allowed only when…</option>
            </Select>
          </Field>
          <Blocks name="Condition" blocks={draft.blocks} catalogue={cat} subject={draft.category} onChange={(blocks) => set("blocks", blocks)} />

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="How strictly">
              <Select value={draft.strength} onChange={(e) => set("strength", e.target.value as Draft["strength"])}>
                {STRENGTHS.map((s) => (
                  <option key={s.strength} value={s.strength}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Field>
            {draft.strength === "complete" && (
              <Field label="Creation step it holds (optional)" hint="The wizard does not move on from this step until the check is met.">
                <Select value={draft.step} onChange={(e) => set("step", e.target.value)}>
                  <option value="">None: only Finish waits on it</option>
                  {subjectCategories(cat)
                    .filter((c) => c.rated)
                    .map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.name}
                      </option>
                    ))}
                </Select>
              </Field>
            )}
          </div>
          <Field label="Message the player sees" hint="{name} stands for the trait it is about.">
            <Input value={draft.message} maxLength={500} placeholder={text || "Pliable Blood can only be taken at character creation."} onChange={(e) => set("message", e.target.value)} />
          </Field>

          <section aria-label="Preview" className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/5 p-3 text-sm">
            <h4 className="text-gold">In plain words</h4>
            {problem && <p className="text-blood-bright">{problem}</p>}
            {!problem && text && <p className="text-parchment">{text}</p>}
            <ErrorText error={preview.error} />
            {!problem && preview.data && body && (
              <>
                {preview.data.breaking.length === 0 ? (
                  <p className="text-xs text-mist">None of the troupe's characters breaks it now.</p>
                ) : (
                  <div className="text-xs">
                    <p className="text-gold">
                      It would flag {preview.data.breaking.length === 1 ? "this character" : `these ${preview.data.breaking.length} characters`}; nothing on their
                      sheets changes:
                    </p>
                    <ul aria-label="Characters it would flag" className="mt-1 list-disc pl-5">
                      {preview.data.breaking.map((b) => (
                        <li key={b.character_id}>
                          {b.name}
                          {b.kind === "npc" ? " (NPC)" : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </section>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!body || !draft.message.trim() || save.isPending}>
              {editing === "new" ? "Add the check" : "Save"}
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

/** Blocks side by side, all of which must hold, with a picker to add another. */
function Blocks({
  name,
  blocks,
  catalogue,
  subject,
  onChange,
  depth = 0,
}: {
  name: string;
  blocks: CondBlock[];
  catalogue: CatalogueOut;
  subject: string;
  onChange: (blocks: CondBlock[]) => void;
  depth?: number;
}) {
  const offered = COND_TYPES.filter((t) => depth < 4 || !["not", "any_of", "all_of"].includes(t.type));
  return (
    <fieldset className={`flex flex-col gap-2 ${depth ? "border-l-2 border-ash pl-3" : ""}`}>
      {depth === 0 && <legend className="mb-1 text-sm text-mist">The condition (every block must hold)</legend>}
      {blocks.length > 0 && (
        <ul className="flex flex-col gap-2">
          {blocks.map((b, i) => (
            <BlockRow
              key={i}
              name={`${name} ${i + 1}`}
              block={b}
              catalogue={catalogue}
              subject={subject}
              depth={depth}
              onChange={(next) => onChange(blocks.map((x, j) => (j === i ? next : x)))}
              onRemove={() => onChange(blocks.filter((_, j) => j !== i))}
            />
          ))}
        </ul>
      )}
      <Select aria-label={`${name}: add a block`} value="" onChange={(e) => e.target.value && onChange([...blocks, newCondBlock(e.target.value as CondType)])} className="sm:w-80">
        <option value="">Add a block…</option>
        {offered.map((t) => (
          <option key={t.type} value={t.type}>
            {t.label}
          </option>
        ))}
      </Select>
    </fieldset>
  );
}

function BlockRow({
  name,
  block,
  catalogue,
  subject,
  depth,
  onChange,
  onRemove,
}: {
  name: string;
  block: CondBlock;
  catalogue: CatalogueOut;
  subject: string;
  depth: number;
  onChange: (block: CondBlock) => void;
  onRemove: () => void;
}) {
  const label = COND_TYPES.find((t) => t.type === block.type)?.label ?? block.type;
  let body: ReactNode = null;
  switch (block.type) {
    case "clan":
      body = <TraitList name={name} label="Clans and bloodlines" options={clans(catalogue)} names={block.names} onChange={(n) => onChange({ ...block, names: n })} />;
      break;
    case "clan_family":
      body = (
        <TraitList
          name={name}
          label="Clans (each with its bloodlines)"
          options={[...new Set(clans(catalogue).map((c) => c.split(":")[0]!.trim()))].sort()}
          names={block.names}
          onChange={(n) => onChange({ ...block, names: n })}
        />
      );
      break;
    case "self":
      body = <TraitList name={name} label="Traits" options={namesIn(catalogue, subject)} names={block.names} onChange={(n) => onChange({ ...block, names: n })} />;
      break;
    case "has": {
      const top = block.name ? topRating(catalogue, block.category, block.name) : null;
      body = (
        <>
          <Labelled label="Kind of trait">
            <Select aria-label={`${name}: kind of trait`} value={block.category} onChange={(e) => onChange({ ...block, category: e.target.value, name: "", rating: null })}>
              {subjectCategories(catalogue).map((c) => (
                <option key={c.key} value={c.key}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Labelled>
          <Labelled label="Trait">
            <Select aria-label={`${name}: trait`} value={block.name} onChange={(e) => onChange({ ...block, name: e.target.value, rating: null })}>
              <option value="">Choose…</option>
              {namesIn(catalogue, block.category).map((n) => (
                <option key={n}>{n}</option>
              ))}
            </Select>
          </Labelled>
          {top !== null && (
            <Labelled label="At least">
              <Select aria-label={`${name}: at least`} value={block.rating ?? ""} onChange={(e) => onChange({ ...block, rating: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Any rating</option>
                {numbers(1, top).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </Labelled>
          )}
        </>
      );
      break;
    }
    case "generation_gte":
    case "generation_lte":
      body = (
        <Labelled label="Generation background">
          <Select aria-label={`${name}: Generation`} value={block.value} onChange={(e) => onChange({ ...block, value: Number(e.target.value) })}>
            {numbers(1, 5).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Labelled>
      );
      break;
    case "copies":
      body = (
        <Labelled label="Held at least">
          <Select aria-label={`${name}: times held`} value={block.value} onChange={(e) => onChange({ ...block, value: Number(e.target.value) })}>
            {numbers(2, 5).map((n) => (
              <option key={n} value={n}>
                {n} times
              </option>
            ))}
          </Select>
        </Labelled>
      );
      break;
    case "not":
    case "any_of":
    case "all_of":
      body = (
        <div className="sm:col-span-2">
          <p className="mb-1 text-xs text-mist">
            {block.type === "not" ? (block.blocks.length > 1 ? "These do not all hold together:" : "This does not hold:") : block.type === "any_of" ? "At least one of these holds:" : "All of these hold:"}
          </p>
          <Blocks name={name} blocks={block.blocks} catalogue={catalogue} subject={subject} depth={depth + 1} onChange={(blocks) => onChange({ ...block, blocks })} />
        </div>
      );
      break;
    case "finished":
      break;
  }
  return (
    <li className="flex flex-col gap-2 rounded-md border border-ash p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-parchment">
          <span className="sr-only">{name}: </span>
          {label.replace("…", "")}
        </span>
        <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove ${name.toLowerCase()}`} onClick={onRemove}>
          Remove
        </Button>
      </div>
      {body && <div className="grid gap-3 sm:grid-cols-2">{body}</div>}
    </li>
  );
}
