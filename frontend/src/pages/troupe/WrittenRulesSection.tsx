import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { WrittenRuleOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { Explainer } from "../../components/Explainer";
import { Markdown } from "../../components/Markdown";
import { Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { SECTIONS } from "../rules/rulesBrowser";
import { RuleAbout } from "./WrittenRulesList";
import { bySection, sectionLabel, sectionsInUse } from "./writtenRules";

type Draft = { section: string; title: string; body: string; category: string; trait: string; page: string };

const blank: Draft = { section: "", title: "", body: "", category: "", trait: "", page: "" };

/** A rule as the editor starts from it. */
export function draftOf(rule: WrittenRuleOut): Draft {
  return {
    section: rule.section,
    title: rule.title,
    body: rule.body,
    category: rule.trait?.category ?? "",
    trait: rule.trait?.name ?? "",
    page: rule.page ?? "",
  };
}

/** What the server is sent for a draft: a trait only when both its category and name are given. */
export function bodyOf(draft: Draft) {
  const trait = draft.category && draft.trait.trim() ? { splat: "vampire", category: draft.category, name: draft.trait.trim() } : null;
  return { section: draft.section.trim(), title: draft.title.trim(), body: draft.body, trait, page: draft.page.trim() || null };
}

/**
 * The troupe's written house rules (#434): rules in words alone, which its players
 * read on the House rules tab and in the rules browser, by section. Storytellers
 * add, edit, reorder within a section and delete them, and choose whether the
 * troupe's profile shows them.
 */
export function WrittenRulesSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const written = useQuery({
    queryKey: ["written-rules", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/written-rules", path)),
  });
  const [editing, setEditing] = useState<WrittenRuleOut | "new" | null>(null);
  const [deleting, setDeleting] = useState<WrittenRuleOut | null>(null);
  const move = useAction((body: { rule: WrittenRuleOut; move: "up" | "down" }) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/written-rules/{rule_id}", {
        params: { path: { troupe_id: troupeId, rule_id: body.rule.id } },
        body: { ...bodyOf(draftOf(body.rule)), move: body.move },
      }),
    ),
  );
  const remove = useAction(async (rule: WrittenRuleOut) => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/written-rules/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: rule.id } } }));
    setDeleting(null);
  });
  const publish = useAction((show: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/written-rules-public", { ...path, body: { public: show } })));
  if (written.isPending) return <Loading />;
  if (written.error) return <ErrorText error={written.error} />;
  const { rules, public: shown } = written.data;
  const sections = bySection(rules);

  return (
    <div className="flex flex-col gap-6">
      <Explainer id="rules-written" title="How written rules work">
        <p className="text-sm">
          Rules your players simply read, with nothing to build: how Crafts difficulties work here, what holding a location allows, your FAQ. Players read them on
          the troupe's{" "}
          <Link to={`/troupes/${troupeId}/house-rules`} className="underline hover:text-parchment">
            House rules
          </Link>{" "}
          tab, by section, and find them in the rules browser. One linked to a trait shows on that trait's details too.
        </p>
        <p className="mt-2 text-sm text-mist">Write them in Markdown: **bold**, *italics*, lists and links.</p>
      </Explainer>
      <Card
        title="Written rules"
        actions={
          canEdit && (
            <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing("new")}>
              Add a rule
            </Button>
          )
        }
      >
        <label className="mb-3 flex min-h-10 items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={shown} disabled={!canEdit || publish.isPending} onChange={(e) => publish.mutate(e.target.checked)} />
          <span>
            Show them on the troupe's profile
            <span className="block text-xs text-mist">So people thinking of joining can read them. If the profile is public, anyone can.</span>
          </span>
        </label>
        <ErrorText error={publish.error ?? move.error} />
        {rules.length === 0 ? (
          <EmptyState title="No written rules yet.">{canEdit ? "Add one for your players to read." : "The storytellers have written none."}</EmptyState>
        ) : (
          sections.map((s) => (
            <section key={s.section} className="not-first:mt-4">
              <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{sectionLabel(s.section)}</h3>
              <ul className="divide-y divide-ash">
                {s.rules.map((r, n) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                    <span className="min-w-40 flex-1">
                      <span className="text-parchment">{r.title}</span>
                      <RuleAbout rule={r} />
                    </span>
                    {canEdit && (
                      <span className="flex shrink-0 items-center gap-1">
                        <Button
                          variant="ghost"
                          className="min-h-8 px-2"
                          aria-label={`Move ${r.title} up`}
                          disabled={n === 0 || move.isPending}
                          onClick={() => move.mutate({ rule: r, move: "up" })}
                        >
                          ↑
                        </Button>
                        <Button
                          variant="ghost"
                          className="min-h-8 px-2"
                          aria-label={`Move ${r.title} down`}
                          disabled={n === s.rules.length - 1 || move.isPending}
                          onClick={() => move.mutate({ rule: r, move: "down" })}
                        >
                          ↓
                        </Button>
                        <Button variant="secondary" className="min-h-8 px-3" aria-label={`Edit ${r.title}`} onClick={() => setEditing(r)}>
                          Edit
                        </Button>
                        <Button variant="ghost" className="min-h-8 px-2" aria-label={`Delete ${r.title}`} onClick={() => setDeleting(r)}>
                          Delete
                        </Button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </Card>
      <Dialog title={editing === "new" ? "Add a written rule" : `Edit ${editing?.title ?? ""}`} open={editing !== null} onClose={() => setEditing(null)} wide phoneFull>
        {editing !== null && (
          <RuleEditor troupeId={troupeId} rule={editing === "new" ? null : editing} sections={sectionsInUse(rules)} onDone={() => setEditing(null)} />
        )}
      </Dialog>
      <Dialog title={`Delete ${deleting?.title ?? ""}?`} open={deleting !== null} onClose={() => setDeleting(null)}>
        <p className="text-sm">Players will no longer read it. This cannot be undone.</p>
        <ErrorText error={remove.error} />
        <div className="mt-4 flex gap-2">
          <Button onClick={() => deleting && remove.mutate(deleting)} disabled={remove.isPending}>
            Delete it
          </Button>
          <Button variant="ghost" onClick={() => setDeleting(null)}>
            Keep it
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

/** Add a rule, or change one: its section, title, body in Markdown, and the trait or page it is about. */
function RuleEditor({ troupeId, rule, sections, onDone }: { troupeId: string; rule: WrittenRuleOut | null; sections: string[]; onDone: () => void }) {
  const [draft, setDraft] = useState<Draft>(rule ? draftOf(rule) : blank);
  const [preview, setPreview] = useState(false);
  const set = (change: Partial<Draft>) => setDraft((d) => ({ ...d, ...change }));
  const sectionList = useId();
  const traitList = useId();
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: { troupe_id: troupeId } } })),
    staleTime: 5 * 60_000,
  });
  const categories = SECTIONS.flatMap((s) => s.categories)
    .map((key) => catalogue.data?.categories.find((c) => c.key === key))
    .filter((c) => c !== undefined);
  const names = (catalogue.data?.traits ?? []).filter((t) => t.category === draft.category).map((t) => t.name);
  const save = useAction(async () => {
    const body = bodyOf(draft);
    if (rule) {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/written-rules/{rule_id}", { params: { path: { troupe_id: troupeId, rule_id: rule.id } }, body: { ...body, move: null } }),
      );
    } else {
      await unwrap(api.POST("/api/troupes/{troupe_id}/written-rules", { params: { path: { troupe_id: troupeId } }, body }));
    }
    onDone();
  });

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Title">
          <Input required maxLength={200} value={draft.title} onChange={(e) => set({ title: e.target.value })} />
        </Field>
        <Field label="Section" hint="Such as Disciplines, Status or FAQ. Leave it empty for none.">
          <Input list={sectionList} maxLength={100} value={draft.section} onChange={(e) => set({ section: e.target.value })} />
        </Field>
        <datalist id={sectionList}>
          {sections.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
      <div className="flex flex-col gap-1 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="text-mist">{preview ? "How players will read it" : "The rule, in Markdown"}</span>
          <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => setPreview(!preview)}>
            {preview ? "Write" : "Preview"}
          </Button>
        </div>
        {preview ? (
          <div className="min-h-32 rounded-md border border-ash p-3">{draft.body.trim() ? <Markdown text={draft.body} /> : <span className="text-mist">Nothing written yet.</span>}</div>
        ) : (
          <Textarea aria-label="The rule, in Markdown" rows={8} maxLength={20000} value={draft.body} onChange={(e) => set({ body: e.target.value })} />
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="About a trait">
          <Select value={draft.category} onChange={(e) => set({ category: e.target.value, trait: "" })}>
            <option value="">No trait</option>
            {categories.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Which one">
          <Input list={traitList} disabled={!draft.category} value={draft.trait} onChange={(e) => set({ trait: e.target.value })} />
        </Field>
        <datalist id={traitList}>
          {names.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
        <Field label="Book page" hint="Such as 238, or Vol. 2, p. 50.">
          <Input maxLength={300} value={draft.page} onChange={(e) => set({ page: e.target.value })} />
        </Field>
      </div>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {rule ? "Save" : "Add it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
