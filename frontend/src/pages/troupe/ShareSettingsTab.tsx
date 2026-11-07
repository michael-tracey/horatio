import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SettingsDocument, ShareImportOut, ShareReviewItemOut, ShareReviewOut, ShareSectionOut, TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { abilities } from "./roles";
import {
  counts,
  countsText,
  fieldText,
  fileName,
  itemOf,
  keyOf,
  matches,
  matchesText,
  replaceAll,
  suggestion,
  tickable,
  ticksFor,
  withField,
  withSections,
} from "./shareSettings";

// The most a file may be, as the server takes it.
const MAX_BYTES = 2 * 1024 * 1024;

/**
 * Customise › Share settings (#521): the troupe's customisation, exported as a file
 * any storyteller can import, even on another Horatio; and importing a file, or
 * another troupe its storyteller runs, into this one, merging. Running staff export;
 * storytellers import.
 */
export function ShareSettingsTab({ troupe, canImport }: { troupe: TroupeOut; canImport: boolean }) {
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-mist">
        Share this troupe's house rules, costs, wording and the rest of Customise with another troupe: start a new chronicle from these rules, or give them to another
        storyteller. An import merges: what matches is changed, the rest is added, and nothing else is reset or removed.{" "}
        <Link to={manualLink("running-a-troupe", "customise-share-settings")} className="underline hover:text-parchment">
          What is and isn't carried
        </Link>
      </p>
      <ExportCard troupe={troupe} />
      {canImport ? (
        <ImportCard troupe={troupe} />
      ) : (
        <Card title="Import">
          <p className="text-sm text-mist">{troupe.archived ? "Nothing can be imported into an archived troupe." : "The troupe's storytellers import settings."}</p>
        </Card>
      )}
    </div>
  );
}

function useExport(troupeId: string, enabled = true) {
  return useQuery({
    queryKey: ["settings-share", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/settings-share", { params: { path: { troupe_id: troupeId } } })),
    enabled,
  });
}

function download(document_: SettingsDocument, troupe: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(document_, null, 2)], { type: "application/json" }));
  link.download = fileName(troupe, new Date());
  link.click();
  URL.revokeObjectURL(link.href);
}

/** Sections in their groups, as Customise has them: the Troupe settings page's, then each of the others. */
function grouped<T extends { group?: string | null }>(sections: T[]): { group: string | null; sections: T[] }[] {
  const found: { group: string | null; sections: T[] }[] = [];
  for (const section of sections) {
    const group = section.group ?? null;
    const last = found[found.length - 1];
    if (group && last?.group === group) last.sections.push(section);
    else found.push({ group, sections: [section] });
  }
  return found;
}

/** A checkbox that shows "some" as well as all or none. */
function TriState({ checked, some, label, disabled, onChange }: { checked: boolean; some: boolean; label: string; disabled?: boolean; onChange: (on: boolean) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = some && !checked;
  }, [some, checked]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />;
}

// --- export ------------------------------------------------------------------------------

function ExportCard({ troupe }: { troupe: TroupeOut }) {
  const found = useExport(troupe.id);
  const [unticked, setUnticked] = useState<Set<string>>(new Set());
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const sections = found.data.sections.filter((s) => s.count > 0);
  const chosen = new Set(sections.filter((s) => !unticked.has(s.key)).map((s) => s.key));
  const set = (keys: string[], on: boolean) =>
    setUnticked((now) => {
      const next = new Set(now);
      for (const key of keys) {
        if (on) next.delete(key);
        else next.add(key);
      }
      return next;
    });

  return (
    <Card title="Export">
      {sections.length === 0 ? (
        <p className="text-sm text-mist">Everything here is as Horatio has it by default: there is nothing to export yet.</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-mist">
            Downloads a file of what differs from Horatio's default, for any storyteller to import. Untick a section to leave it out. Sections still at the default aren't
            listed.
          </p>
          <ExportChecklist sections={sections} chosen={chosen} onChange={set} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => download(withSections(found.data.document, chosen), troupe.name)} disabled={chosen.size === 0}>
              Export
            </Button>
            <span className="text-sm text-mist">{fileName(troupe.name, new Date())}</span>
          </div>
        </>
      )}
    </Card>
  );
}

function ExportChecklist({ sections, chosen, onChange }: { sections: ShareSectionOut[]; chosen: Set<string>; onChange: (keys: string[], on: boolean) => void }) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="sr-only">Sections to export</legend>
      {grouped(sections).map(({ group, sections: inside }) =>
        group ? (
          <div key={group} className="flex flex-col gap-1.5">
            <label className="flex items-center gap-2 text-sm">
              <TriState
                label={group}
                checked={inside.every((s) => chosen.has(s.key))}
                some={inside.some((s) => chosen.has(s.key))}
                onChange={(on) => onChange(
                  inside.map((s) => s.key),
                  on,
                )}
              />
              <span aria-hidden>{group}</span>
            </label>
            <div className="ml-6 flex flex-col gap-1.5">
              {inside.map((s) => (
                <SectionTick key={s.key} section={s} on={chosen.has(s.key)} onChange={(on) => onChange([s.key], on)} />
              ))}
            </div>
          </div>
        ) : (
          inside.map((s) => <SectionTick key={s.key} section={s} on={chosen.has(s.key)} onChange={(on) => onChange([s.key], on)} />)
        ),
      )}
    </fieldset>
  );
}

function SectionTick({ section, on, onChange }: { section: ShareSectionOut; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      {section.label}
      <span className="text-mist">({section.count})</span>
    </label>
  );
}

// --- import ------------------------------------------------------------------------------

type Source = { file_name: string } | { from_troupe_id: string; name: string };

function ImportCard({ troupe }: { troupe: TroupeOut }) {
  const [loaded, setLoaded] = useState<{ document: SettingsDocument; source: Source } | null>(null);
  const [done, setDone] = useState<ShareImportOut | null>(null);
  return (
    <Card title="Import">
      {done && !loaded && (
        <p role="status" className="mb-3 text-sm text-gold">
          Imported: {done.added} added, {done.changed} changed{done.sections.length > 0 && ` (${done.sections.map((s) => s.label).join(", ")})`}.
        </p>
      )}
      {loaded ? (
        <Review
          troupe={troupe}
          loaded={loaded}
          onCancel={() => setLoaded(null)}
          onDone={(result) => {
            setDone(result);
            setLoaded(null);
          }}
        />
      ) : (
        <ChooseSource
          troupe={troupe}
          onLoad={(found) => {
            setDone(null);
            setLoaded(found);
          }}
        />
      )}
    </Card>
  );
}

function ChooseSource({ troupe, onLoad }: { troupe: TroupeOut; onLoad: (found: { document: SettingsDocument; source: Source }) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [other, setOther] = useState("");
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const running = (troupes.data ?? []).filter((t) => t.id !== troupe.id && !t.archived && abilities(t.my_role, false).running);
  const copy = useMutation({
    mutationFn: (troupeId: string) => unwrap(api.GET("/api/troupes/{troupe_id}/settings-share", { params: { path: { troupe_id: troupeId } } })),
  });

  const read = async (file: File) => {
    setProblem(null);
    if (file.size > MAX_BYTES) return setProblem("That file is too large to be a troupe's settings.");
    try {
      onLoad({ document: JSON.parse(await file.text()) as SettingsDocument, source: { file_name: file.name } });
    } catch {
      setProblem("That file isn't a troupe's settings: choose a .json file exported from Horatio.");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">Import from a file exported from Horatio, or copy straight from another troupe you run. Either way, you choose what comes in before anything is saved.</p>
      <div className="flex flex-col gap-2">
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          aria-label="Settings file"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void read(file);
          }}
        />
        <div>
          <Button variant="secondary" onClick={() => input.current?.click()}>
            Choose a file…
          </Button>
        </div>
        {problem && <ErrorText error={problem} />}
      </div>
      {running.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Or copy from a troupe you run">
            <Select value={other} onChange={(e) => setOther(e.target.value)} className="w-64 max-w-full">
              <option value="">Choose a troupe</option>
              {running.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Button
            variant="secondary"
            disabled={!other || copy.isPending}
            onClick={() =>
              copy.mutate(other, {
                onSuccess: (found) => onLoad({ document: found.document, source: { from_troupe_id: other, name: running.find((t) => t.id === other)?.name ?? "" } }),
              })
            }
          >
            Review its settings
          </Button>
        </div>
      )}
      <ErrorText error={copy.error ?? troupes.error} />
    </div>
  );
}

function Review({
  troupe,
  loaded,
  onCancel,
  onDone,
}: {
  troupe: TroupeOut;
  loaded: { document: SettingsDocument; source: Source };
  onCancel: () => void;
  onDone: (result: ShareImportOut) => void;
}) {
  const [document_, setDocument] = useState(loaded.document);
  const [review, setReview] = useState<ShareReviewOut | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const toast = useToast();
  const check = useMutation({
    mutationFn: (body: SettingsDocument) =>
      unwrap(api.POST("/api/troupes/{troupe_id}/settings-share/review", { params: { path: { troupe_id: troupe.id } }, body: { document: body } })),
  });
  const apply = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/settings-share/apply", {
        params: { path: { troupe_id: troupe.id } },
        body: {
          document: document_,
          items: [...ticked].map((key) => {
            const [section, index] = key.split(":");
            return { section: section as ShareReviewItemOut["section"], index: Number(index) };
          }),
          ...("file_name" in loaded.source ? { file_name: loaded.source.file_name } : { from_troupe_id: loaded.source.from_troupe_id }),
        },
      }),
    ),
  );

  // Reviewed once loaded, and again after each edit, so each item says where it stands.
  const reviewAgain = (next: SettingsDocument) => {
    setDocument(next);
    check.mutate(next, {
      onSuccess: (found) => {
        setTicked((now) => ticksFor(found, review ? { review, ticked: now } : undefined));
        setReview(found);
      },
    });
  };
  const first = useRef(false);
  useEffect(() => {
    if (first.current) return;
    first.current = true;
    // Only once, as it loads.
    reviewAgain(loaded.document);
  }, []);

  const from = "file_name" in loaded.source ? loaded.source.file_name : loaded.source.name;
  const heading = (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm">
        From <span className="text-parchment">{document_.troupe || "another troupe"}</span>
        {from && from !== document_.troupe && <span className="text-mist"> ({from})</span>}
      </p>
      <Button variant="ghost" onClick={onCancel}>
        Choose another
      </Button>
    </div>
  );
  if (!review) {
    return (
      <>
        {heading}
        {check.error ? <ErrorText error={check.error} /> : <Loading />}
      </>
    );
  }

  const items = review.sections.flatMap((s) => s.items);
  const total = counts(items, ticked);
  const toggle = (keys: string[], on: boolean) =>
    setTicked((now) => {
      const next = new Set(now);
      for (const key of keys) {
        if (on) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  const all = items.filter(tickable).map(keyOf);

  return (
    <div className="flex flex-col gap-4">
      {heading}
      {review.warnings.map((w) => (
        <Notice key={w}>{w}</Notice>
      ))}
      <FindReplace
        document={document_}
        items={items}
        ticked={ticked}
        here={troupe.name}
        busy={check.isPending}
        onReplace={(find, replacement) => {
          reviewAgain(replaceAll(document_, items, ticked, find, replacement));
          toast({ message: `Replaced “${find}” with “${replacement}”` });
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" className="min-h-8 px-3" onClick={() => toggle(all, true)}>
          Select all
        </Button>
        <Button variant="secondary" className="min-h-8 px-3" onClick={() => toggle(all, false)}>
          Select none
        </Button>
      </div>
      <div role="group" aria-label="What to import" className="flex flex-col gap-3">
        {grouped(review.sections).map(({ group, sections }) =>
          group ? (
            <div key={group} className="flex flex-col gap-2 rounded-lg border border-ash p-3">
              <SectionHeader label={group} items={sections.flatMap((s) => s.items)} ticked={ticked} onChange={toggle} />
              <div className="flex flex-col gap-2 sm:ml-6">
                {sections.map((s) => (
                  <ReviewSection key={s.key} label={s.label} items={s.items} ticked={ticked} document={document_} onToggle={toggle} onEdit={reviewAgain} />
                ))}
              </div>
            </div>
          ) : (
            sections.map((s) => (
              <div key={s.key} className="rounded-lg border border-ash p-3">
                <ReviewSection label={s.label} items={s.items} ticked={ticked} document={document_} onToggle={toggle} onEdit={reviewAgain} />
              </div>
            ))
          ),
        )}
      </div>
      <ErrorText error={check.error} />
      <div className="flex flex-col gap-2 border-t border-ash pt-4">
        <p className="text-sm" role="status">
          {countsText(total)}.
        </p>
        <p className="text-sm text-mist">
          <BackupLink troupe={troupe} /> as a backup, before you import.
        </p>
        <div>
          <Button disabled={(!total.adds && !total.changes) || apply.isPending || check.isPending} onClick={() => apply.mutate(undefined, { onSuccess: onDone })}>
            {apply.isPending ? "Importing…" : "Import"}
          </Button>
        </div>
        <ErrorText error={apply.error} />
      </div>
    </div>
  );
}

/** Downloads this troupe's own settings, all of them. */
function BackupLink({ troupe }: { troupe: TroupeOut }) {
  const [wanted, setWanted] = useState(false);
  const found = useExport(troupe.id, wanted);
  useEffect(() => {
    if (wanted && found.data) {
      download(found.data.document, troupe.name);
      setWanted(false);
    }
  }, [wanted, found.data, troupe.name]);
  return (
    <button type="button" className="text-parchment underline hover:text-gold" onClick={() => (found.data ? download(found.data.document, troupe.name) : setWanted(true))}>
      Download this troupe's settings first
    </button>
  );
}

function SectionHeader({ label, items, ticked, onChange }: { label: string; items: ShareReviewItemOut[]; ticked: Set<string>; onChange: (keys: string[], on: boolean) => void }) {
  const keys = items.filter(tickable).map(keyOf);
  const on = keys.filter((k) => ticked.has(k)).length;
  return (
    <label className="flex items-center gap-2 text-sm">
      <TriState label={label} checked={keys.length > 0 && on === keys.length} some={on > 0} disabled={keys.length === 0} onChange={(now) => onChange(keys, now)} />
      <span aria-hidden className="text-gold">
        {label}
      </span>
    </label>
  );
}

function ReviewSection({
  label,
  items,
  ticked,
  document,
  onToggle,
  onEdit,
}: {
  label: string;
  items: ShareReviewItemOut[];
  ticked: Set<string>;
  document: SettingsDocument;
  onToggle: (keys: string[], on: boolean) => void;
  onEdit: (next: SettingsDocument) => void;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const keys = items.filter(tickable).map(keyOf);
  const on = keys.filter((k) => ticked.has(k)).length;
  return (
    <section aria-label={label} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <TriState label={label} checked={keys.length > 0 && on === keys.length} some={on > 0} disabled={keys.length === 0} onChange={(now) => onToggle(keys, now)} />
          <span aria-hidden>{label}</span>
          <span className="text-mist">
            ({on} of {items.length})
          </span>
        </label>
        <Button variant="ghost" className="min-h-8 px-2" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(!open)}>
          {open ? "Hide items" : "Show items"}
          <span className="sr-only"> of {label}</span>
        </Button>
      </div>
      {open && (
        <ul id={listId} className="flex flex-col divide-y divide-ash border-t border-ash">
          {items.map((item) => (
            <ReviewRow key={keyOf(item)} item={item} on={ticked.has(keyOf(item))} document={document} onToggle={(now) => onToggle([keyOf(item)], now)} onEdit={onEdit} />
          ))}
        </ul>
      )}
    </section>
  );
}

const STATUS: Record<ShareReviewItemOut["status"], { label: string; tone: "gold" | "mist" | "blood" }> = {
  new: { label: "New", tone: "gold" },
  changes: { label: "Changes yours", tone: "gold" },
  same: { label: "Same as yours", tone: "mist" },
  cannot: { label: "Can't import", tone: "blood" },
};

function ReviewRow({
  item,
  on,
  document,
  onToggle,
  onEdit,
}: {
  item: ShareReviewItemOut;
  on: boolean;
  document: SettingsDocument;
  onToggle: (on: boolean) => void;
  onEdit: (next: SettingsDocument) => void;
}) {
  const [editing, setEditing] = useState(false);
  const status = STATUS[item.status];
  const fields = item.editable;
  const value = itemOf(document, item.section, item.index);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const begin = () => {
    setDraft(Object.fromEntries(fields.map((f) => [f.field, fieldText(value, f)])));
    setEditing(true);
  };
  const save = () => {
    let next = document;
    for (const f of fields) if (draft[f.field] !== fieldText(value, f)) next = withField(next, item.section, item.index, f, draft[f.field] ?? "");
    setEditing(false);
    if (next !== document) onEdit(next);
  };
  return (
    <li className="flex flex-col gap-1.5 py-2.5 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <label className="flex min-w-0 flex-1 items-start gap-2">
          <input type="checkbox" className="mt-1" checked={on} disabled={!tickable(item)} onChange={(e) => onToggle(e.target.checked)} />
          <span className="min-w-0 break-words text-parchment">{item.label}</span>
        </label>
        <span className="flex items-center gap-2">
          <Badge tone={status.tone}>{status.label}</Badge>
          {fields.length > 0 && !editing && item.status !== "cannot" && (
            <Button variant="ghost" className="min-h-8 px-2" onClick={begin}>
              Edit<span className="sr-only"> {item.label}</span>
            </Button>
          )}
        </span>
      </div>
      {item.status === "cannot" && item.reason && <p className="ml-6 text-xs text-blood-bright">{item.reason}</p>}
      {item.status === "changes" && (
        <dl className="ml-6 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-mist">Yours</dt>
          <dd className="break-words">{item.before}</dd>
          <dt className="text-mist">Becomes</dt>
          <dd className="break-words text-parchment">{item.after}</dd>
        </dl>
      )}
      {editing && (
        <div className="ml-6 flex flex-col gap-2">
          {fields.map((f) =>
            f.multiline ? (
              <Field key={f.field} label={f.label}>
                <Textarea rows={f.lines ? 6 : 4} value={draft[f.field] ?? ""} onChange={(e) => setDraft({ ...draft, [f.field]: e.target.value })} />
              </Field>
            ) : (
              <Field key={f.field} label={f.label}>
                <Input value={draft[f.field] ?? ""} onChange={(e) => setDraft({ ...draft, [f.field]: e.target.value })} />
              </Field>
            ),
          )}
          <div className="flex gap-2">
            <Button className="min-h-8 px-3" onClick={save}>
              Done
            </Button>
            <Button variant="ghost" className="min-h-8 px-3" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function FindReplace({
  document,
  items,
  ticked,
  here,
  busy,
  onReplace,
}: {
  document: SettingsDocument;
  items: ShareReviewItemOut[];
  ticked: Set<string>;
  here: string;
  busy: boolean;
  onReplace: (find: string, replacement: string) => void;
}) {
  const [find, setFind] = useState("");
  const [replacement, setReplacement] = useState("");
  const found = matches(document, items, ticked, find);
  const offer = suggestion(document, items, ticked, here);
  return (
    <section aria-label="Find and replace" className="flex flex-col gap-2 rounded-lg border border-ash p-3">
      <h3 className="text-sm text-gold">Find and replace</h3>
      <p className="text-xs text-mist">In the text of the ticked items: names, descriptions, house wording and the rest. Case matters.</p>
      {offer && offer !== find && (
        <p className="text-sm">
          The text names {offer}.{" "}
          <button
            type="button"
            className="text-parchment underline hover:text-gold"
            onClick={() => {
              setFind(offer);
              setReplacement(here);
            }}
          >
            Replace “{offer}” with “{here}”
          </button>
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Find">
          <Input value={find} onChange={(e) => setFind(e.target.value)} />
        </Field>
        <Field label="Replace with">
          <Input value={replacement} onChange={(e) => setReplacement(e.target.value)} />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" className="min-h-8 px-3" disabled={!find || found.matches === 0 || busy} onClick={() => onReplace(find, replacement)}>
          Replace all
        </Button>
        {find && (
          <span role="status" className="text-sm text-mist">
            {matchesText(found)}
          </span>
        )}
      </div>
    </section>
  );
}
