import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { LocationCatalogueOut, LocationQualityOut, OwnLocationQualityOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { fullSuggestion, parseSuggestions, suggestionLines, suggestionText } from "./locations";

const LIMITS = [
  { value: "refuse", label: "Refuse", meaning: "A character can't take control of a location that would put them over their limit. Staff see why." },
  { value: "note", label: "Only note it", meaning: "Allowed. Staff are told when they save, and the troupe's log notes it." },
] as const;

const KINDS = [
  { value: "standard", label: "Standard" },
  { value: "iconic", label: "Iconic" },
  { value: "supernatural", label: "Supernatural" },
  { value: "elysium", label: "Elysium" },
] as const;

/**
 * The troupe's house rules for locations: the house options that change the
 * book (all on unless switched off), what going over the control limit does, the
 * troupe's own qualities, and the whole catalogue as played here.
 */
export function LocationRulesSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const catalogue = useQuery({
    queryKey: ["location-catalogue", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/locations/catalogue", path)),
  });
  const option = useAction((body: { key: string; on: boolean }) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/location-options/{key}", { params: { path: { troupe_id: troupeId, key: body.key } }, body: { on: body.on } })),
  );
  const limit = useAction((strength: "refuse" | "note") => unwrap(api.PUT("/api/troupes/{troupe_id}/location-limit", { ...path, body: { strength } })));
  if (catalogue.isPending) return <Loading />;
  if (catalogue.error) return <ErrorText error={catalogue.error} />;
  const c = catalogue.data;

  return (
    <div className="flex flex-col gap-6">
      <Card title="House options">
        <p className="mb-3 text-sm text-mist">
          Changes to the book's Stock Locations ({c.book}, pp. 117–133) that many troupes play. Each is on unless switched off here.
        </p>
        <ul className="divide-y divide-ash">
          {c.options.map((o) => (
            <li key={o.key} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-start sm:gap-4">
              <span className="min-w-0 flex-1 text-sm">
                <span className="text-parchment">{o.name}</span>
                <span className="block text-mist">{o.text}</span>
              </span>
              {canEdit ? (
                <label className="flex shrink-0 items-center gap-2 text-sm">
                  <input type="checkbox" checked={o.on} disabled={option.isPending} onChange={(e) => option.mutate({ key: o.key, on: e.target.checked })} />
                  {o.on ? "On" : "Off"}
                </label>
              ) : (
                <Badge tone={o.on ? "gold" : "mist"}>{o.on ? "On" : "Off"}</Badge>
              )}
            </li>
          ))}
        </ul>
        <ErrorText error={option.error} />
      </Card>

      <Card title="Control limit">
        <p className="mb-3 text-sm text-mist">
          A character controls up to five locations, and one more for each dot of Retainers (p. {c.pages.control_page ?? "119"}). Havens don't count, nor a conglomerate whose every
          subsidiary they control. Going over the limit:
        </p>
        {canEdit ? (
          <div className="flex flex-col gap-2">
            {LIMITS.map((l) => (
              <label key={l.value} className="flex items-start gap-2 text-sm">
                <input type="radio" name="location-limit" className="mt-1" checked={c.limit === l.value} disabled={limit.isPending} onChange={() => limit.mutate(l.value)} />
                <span>
                  {l.label}
                  <span className="block text-xs text-mist">{l.meaning}</span>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="text-sm">{LIMITS.find((l) => l.value === c.limit)?.label}</p>
        )}
        <ErrorText error={limit.error} />
      </Card>

      <OwnQualities troupeId={troupeId} catalogue={c} canEdit={canEdit} />
      <Catalogue catalogue={c} />
    </div>
  );
}

type OwnDraft = { name: string; kind: (typeof KINDS)[number]["value"]; text: string; detail: string; repeatable: boolean; suggested: string };

const EMPTY: OwnDraft = { name: "", kind: "standard", text: "", detail: "", repeatable: false, suggested: "" };

function OwnQualities({ troupeId, catalogue, canEdit }: { troupeId: string; catalogue: LocationCatalogueOut; canEdit: boolean }) {
  const [editing, setEditing] = useState<string | null>(null);
  const archive = useAction((q: OwnLocationQualityOut) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/location-qualities/{quality_id}/archived", {
        params: { path: { troupe_id: troupeId, quality_id: q.id } },
        body: { archived: !q.archived },
      }),
    ),
  );
  return (
    <Card
      title="The troupe's qualities"
      actions={
        canEdit &&
        editing === null && (
          <Button variant="secondary" onClick={() => setEditing("new")}>
            Add a quality
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">Location qualities of the troupe's own, marked ★, with what a quest for one should ask for.</p>
      {editing === "new" && <OwnForm troupeId={troupeId} quality={null} onDone={() => setEditing(null)} />}
      {catalogue.own.length === 0 && editing !== "new" && <p className="text-sm text-mist">None yet.</p>}
      <ul className="divide-y divide-ash">
        {catalogue.own.map((q) => (
          <li key={q.id} className="py-2.5 text-sm">
            {editing === q.id ? (
              <OwnForm troupeId={troupeId} quality={q} onDone={() => setEditing(null)} />
            ) : (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
                <span className="min-w-0 flex-1">
                  <span className="text-parchment">{q.name} ★</span>
                  <span className="ml-2 text-xs text-mist">
                    {q.kind}
                    {q.archived ? ", archived" : ""} · on {q.held_by} {q.held_by === 1 ? "location" : "locations"}
                  </span>
                  <span className="block text-mist">{q.text}</span>
                  {q.suggested.length > 0 && <span className="block text-xs text-mist">Suggested: {q.suggested.map(suggestionText).join("; ")}</span>}
                </span>
                {canEdit && (
                  <span className="flex shrink-0 gap-1">
                    <Button variant="ghost" className="min-h-8 px-2" aria-label={`Change ${q.name}`} onClick={() => setEditing(q.id)}>
                      Change
                    </Button>
                    <Button variant="ghost" className="min-h-8 px-2" onClick={() => archive.mutate(q)}>
                      {q.archived ? "Bring back" : "Archive"}
                    </Button>
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={archive.error} />
    </Card>
  );
}

function OwnForm({ troupeId, quality, onDone }: { troupeId: string; quality: OwnLocationQualityOut | null; onDone: () => void }) {
  const [d, setD] = useState<OwnDraft>(
    quality ? { name: quality.name, kind: quality.kind, text: quality.text, detail: quality.detail, repeatable: quality.repeatable, suggested: suggestionLines(quality.suggested) } : EMPTY,
  );
  const set = (change: Partial<OwnDraft>) => setD({ ...d, ...change });
  const save = useAction(async () => {
    const body = { name: d.name, kind: d.kind, text: d.text, detail: d.detail, repeatable: d.repeatable, suggested: parseSuggestions(d.suggested).map(fullSuggestion) };
    if (quality) {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/location-qualities/{quality_id}", { params: { path: { troupe_id: troupeId, quality_id: quality.id } }, body }),
      );
    } else {
      await unwrap(api.POST("/api/troupes/{troupe_id}/location-qualities", { params: { path: { troupe_id: troupeId } }, body }));
    }
    onDone();
  });
  return (
    <form
      aria-label={quality ? `Change ${quality.name}` : "Add a location quality"}
      className="mb-3 grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label="Name">
        <Input required value={d.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Kind">
        <Select value={d.kind} onChange={(e) => set({ kind: e.target.value as OwnDraft["kind"] })}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Field label="What it does">
          <Textarea required rows={2} value={d.text} onChange={(e) => set({ text: e.target.value })} />
        </Field>
      </div>
      <Field label="Detail it names (optional)" hint="Such as “Science specialisation”, asked for when it is given to a location.">
        <Input value={d.detail} onChange={(e) => set({ detail: e.target.value })} />
      </Field>
      <label className="flex items-center gap-2 self-center text-sm">
        <input type="checkbox" checked={d.repeatable} onChange={(e) => set({ repeatable: e.target.checked })} />
        Can be taken more than once
      </label>
      <div className="sm:col-span-2">
        <Field label="Suggested requirements" hint="One to a line. “Crafts [2,3,4]” is a trait at a level by the location's rating, lowest first; anything else is kept as words.">
          <Textarea rows={3} value={d.suggested} onChange={(e) => set({ suggested: e.target.value })} />
        </Field>
      </div>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
    </form>
  );
}

/** Every quality as this troupe plays it, with its page and what a quest for it should ask. */
function Catalogue({ catalogue }: { catalogue: LocationCatalogueOut }) {
  const groups = KINDS.map((k) => ({ ...k, qualities: catalogue.qualities.filter((q) => q.kind === k.value) }));
  return (
    <Card title="The catalogue">
      <p className="mb-3 text-sm text-mist">
        Each quality as played here, with its page and what a quest for it should ask for, by the location's rating. A standard location has up to its rating in qualities, a
        prestige or iconic one twice that; only an iconic one has iconic qualities, and no location more than one supernatural quality.
      </p>
      <div className="flex flex-col gap-2">
        {groups.map((g) => (
          <details key={g.value} className="rounded-md border border-ash/60 px-3 py-2">
            <summary className="cursor-pointer text-sm text-gold">
              {g.label} qualities ({g.qualities.length})
            </summary>
            <ul className="mt-2 flex flex-col gap-2 text-sm">
              {g.qualities.map((q) => (
                <QualityRow key={q.name} quality={q} book={catalogue.book} />
              ))}
            </ul>
          </details>
        ))}
        <details className="rounded-md border border-ash/60 px-3 py-2">
          <summary className="cursor-pointer text-sm text-gold">Negative qualities ({catalogue.negatives.length})</summary>
          <ul className="mt-2 flex flex-col gap-2 text-sm">
            {catalogue.negatives.map((n) => (
              <li key={n.name}>
                <span className="text-parchment">{n.name}</span> <span className="text-mist">(p. {n.page})</span>
                <ol className="ml-4 list-decimal text-mist">
                  {n.levels.map((level, i) => (
                    <li key={i}>{level}</li>
                  ))}
                </ol>
                <span className="text-xs text-mist">
                  {n.removed}
                  {n.raised_by ? ` ${n.raised_by} lets it take one more.` : ""}
                </span>
              </li>
            ))}
          </ul>
        </details>
        <details className="rounded-md border border-ash/60 px-3 py-2">
          <summary className="cursor-pointer text-sm text-gold">Haven advantages ({catalogue.haven_advantages.length})</summary>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {catalogue.haven_advantages.map((a) => (
              <li key={a.name}>
                <span className="text-parchment">{a.name}</span> <span className="text-mist">— {a.text} (MET: VTM, p. {a.page})</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </Card>
  );
}

function QualityRow({ quality: q, book }: { quality: LocationQualityOut; book: string }) {
  const notes = [
    q.option && `house option: ${q.option}`,
    q.house && "the troupe's own",
    q.min_rating && `rating ${q.min_rating} or higher`,
    q.per_qualities && `one for each ${q.per_qualities} qualities`,
    !q.counts && q.kind !== "elysium" && "doesn't count toward its qualities",
    q.repeatable && !q.per_qualities && "can be taken again",
    q.excludes.length > 0 && `not with ${q.excludes.join(" or ")}`,
  ].filter(Boolean);
  return (
    <li>
      <span className="text-parchment">
        {q.name}
        {q.house ? " ★" : ""}
      </span>
      {q.page && (
        <span className="text-mist">
          {" "}
          ({book}, p. {q.page})
        </span>
      )}
      <span className="block text-mist">{q.text}</span>
      {notes.length > 0 && <span className="block text-xs text-gold">{notes.join(" · ")}</span>}
      {q.suggested.length > 0 && <span className="block text-xs text-mist">Quest: {q.suggested.map(suggestionText).join("; ")}</span>}
    </li>
  );
}
