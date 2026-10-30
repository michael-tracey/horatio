import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { LocationCatalogueOut, LocationIn, LocationOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { WhoPicker } from "./WhoPicker";

type Kind = LocationIn["kind"];
type Held = "controlled" | "none" | "uncontrollable";
/** A person picked: "c:<character id>", "name" with a name, or "" for nobody. */
type Who = { who: string; name: string };
type Quality = { name: string; detail: string };
type Negative = { name: string; level: number; secret: boolean; by: string };

type Draft = {
  name: string;
  kind: Kind;
  rating: number;
  parent_id: string;
  qualities: Quality[];
  negatives: Negative[];
  held: Held;
  controller: Who;
  joint: Who;
  heir: Who;
  influence_type: "" | "elite" | "underworld";
  influence_area: string;
  address: string;
  web_address: string;
  map_link: string;
  feeding_block: string;
  locked: boolean;
  haven_of_id: string;
  haven_advantages: string[];
  elysium: boolean;
  elysium_since: string;
  notes: string;
};

const NOBODY: Who = { who: "", name: "" };

function whoOf(person: { id?: string | null; name: string } | null): Who {
  if (!person) return NOBODY;
  return person.id ? { who: `c:${person.id}`, name: "" } : { who: "name", name: person.name };
}

function draftOf(l: LocationOut | null): Draft {
  return {
    name: l?.name ?? "",
    kind: l?.kind ?? "standard",
    rating: l?.rating ?? 1,
    parent_id: l?.parent?.id ?? "",
    qualities: l?.qualities.map((q) => ({ name: q.name, detail: q.detail })) ?? [],
    negatives: l?.negatives.map((n) => ({ name: n.name, level: n.level, secret: n.secret, by: n.by })) ?? [],
    held: !l || l.control === "none" ? "none" : l.control === "uncontrollable" ? "uncontrollable" : "controlled",
    controller: whoOf(l?.controller ?? null),
    joint: whoOf(l?.joint ?? null),
    heir: whoOf(l?.heir ?? null),
    influence_type: l?.influence_type ?? "",
    influence_area: l?.influence_area ?? "",
    address: l?.address ?? "",
    web_address: l?.web_address ?? "",
    map_link: l?.map_link ?? "",
    feeding_block: l?.feeding_block ?? "",
    locked: l?.locked ?? false,
    haven_of_id: l?.haven_of?.id ?? "",
    haven_advantages: l?.haven_advantages ?? [],
    elysium: l?.elysium_since != null,
    elysium_since: l?.elysium_since != null ? String(l.elysium_since) : String(new Date().getFullYear()),
    notes: l?.notes ?? "",
  };
}

const idOf = (w: Who) => (w.who.startsWith("c:") ? w.who.slice(2) : null);
const nameOf = (w: Who) => (w.who === "name" ? w.name : "");

function bodyOf(d: Draft): LocationIn {
  const controlled = d.held === "controlled";
  const control = d.held === "controlled" ? (d.controller.who === "name" ? "named" : "character") : d.held;
  return {
    name: d.name,
    kind: d.kind,
    rating: d.rating,
    parent_id: d.parent_id || null,
    qualities: d.qualities,
    negatives: d.negatives,
    control,
    controller_id: controlled ? idOf(d.controller) : null,
    controller_name: controlled ? nameOf(d.controller) : "",
    joint_id: controlled ? idOf(d.joint) : null,
    joint_name: controlled ? nameOf(d.joint) : "",
    heir_id: idOf(d.heir),
    heir_name: nameOf(d.heir),
    influence_type: d.influence_type || null,
    influence_area: d.influence_type ? d.influence_area : "",
    address: d.address,
    web_address: d.web_address,
    map_link: d.map_link,
    feeding_block: d.feeding_block,
    locked: d.locked,
    haven_of_id: d.haven_of_id || null,
    haven_advantages: d.haven_of_id ? d.haven_advantages : [],
    elysium_since: d.elysium && d.elysium_since ? Number(d.elysium_since) : null,
    notes: d.notes,
  };
}

const KIND_HEADINGS: Record<string, string> = { standard: "Standard", iconic: "Iconic", supernatural: "Supernatural", elysium: "Elysium" };

/**
 * Adding or changing a location: everything staff keep about it. The server
 * checks the quality limits and the control limit, and says why it refuses.
 */
export function LocationForm({
  troupeId,
  catalogue,
  others,
  location,
  onSaved,
  onCancel,
}: {
  troupeId: string;
  catalogue: LocationCatalogueOut;
  /** The troupe's other locations, which can be its conglomerate. */
  others: LocationOut[];
  location: LocationOut | null;
  onSaved: (saved: LocationOut, warnings: string[]) => void;
  onCancel?: () => void;
}) {
  const [d, setD] = useState<Draft>(() => draftOf(location));
  const set = (change: Partial<Draft>) => setD({ ...d, ...change });
  const characters = catalogue.characters.map((c) => ({ id: c.id, name: c.name, kind: c.kind, in_troupe: true }));
  const quality = (name: string) => catalogue.qualities.find((q) => q.name === name);
  const type = catalogue.types.find((t) => t.key === d.kind);
  const most = (type?.per_rating ?? 0) * d.rating;
  const counted = d.qualities.filter((q) => {
    const known = quality(q.name);
    return !known || known.counts;
  }).length;
  const conglomerates = catalogue.options.find((o) => o.key === "conglomerates")?.on ?? false;
  const owner = catalogue.characters.find((c) => c.id === d.haven_of_id);
  const havens = catalogue.characters.filter((c) => c.haven > 0 || c.id === d.haven_of_id);
  const areas = d.influence_type ? (catalogue.influence_areas[d.influence_type] ?? []) : [];

  const save = useAction(async () => {
    const body = bodyOf(d);
    const saved = location
      ? await unwrap(api.PATCH("/api/locations/{location_id}", { params: { path: { location_id: location.id } }, body }))
      : await unwrap(api.POST("/api/troupes/{troupe_id}/locations", { params: { path: { troupe_id: troupeId } }, body }));
    onSaved(saved, saved.warnings);
  });

  return (
    <form
      aria-label={location ? `Change ${location.name}` : "Add a location"}
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 font-sans text-xs tracking-wide text-mist uppercase">The place</legend>
        <Field label="Name">
          <Input required value={d.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select value={d.kind} onChange={(e) => set({ kind: e.target.value as Kind })}>
              {catalogue.types.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Rating">
            <Select value={d.rating} onChange={(e) => set({ rating: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {type && <p className="text-xs text-mist sm:col-span-2">{type.text}</p>}
        {(conglomerates || d.parent_id) && (
          <Field label="Conglomerate" hint="The location it is a subsidiary of, if any.">
            <Select value={d.parent_id} onChange={(e) => set({ parent_id: e.target.value })}>
              <option value="">None</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Address">
          <Input value={d.address} onChange={(e) => set({ address: e.target.value })} />
        </Field>
        <Field label="Web address">
          <Input type="url" value={d.web_address} onChange={(e) => set({ web_address: e.target.value })} placeholder="https://" />
        </Field>
        <Field label="Map link">
          <Input type="url" value={d.map_link} onChange={(e) => set({ map_link: e.target.value })} placeholder="https://" />
        </Field>
        <Field label="Feeding block">
          <Input list={`blocks-${troupeId}`} value={d.feeding_block} onChange={(e) => set({ feeding_block: e.target.value })} />
        </Field>
        <datalist id={`blocks-${troupeId}`}>
          {catalogue.feeding_blocks.map((b) => (
            <option key={b} value={b} />
          ))}
        </datalist>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Influence">
            <Select value={d.influence_type} onChange={(e) => set({ influence_type: e.target.value as Draft["influence_type"] })}>
              <option value="">None</option>
              <option value="elite">Elite</option>
              <option value="underworld">Underworld</option>
            </Select>
          </Field>
          {d.influence_type && (
            <Field label="Influence area">
              <Input list={`areas-${troupeId}`} value={d.influence_area} onChange={(e) => set({ influence_area: e.target.value })} />
            </Field>
          )}
          <datalist id={`areas-${troupeId}`}>
            {areas.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
        </div>
        <label className="flex items-start gap-2 text-sm sm:col-span-2">
          <input type="checkbox" className="mt-1" checked={d.locked} onChange={(e) => set({ locked: e.target.checked })} />
          <span>
            Locked
            <span className="block text-xs text-mist">Staff are holding it: no quest may target it.</span>
          </span>
        </label>
      </fieldset>

      {d.kind !== "haven" && (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 font-sans text-xs tracking-wide text-mist uppercase">
            Qualities · {counted} of {most}
          </legend>
          {d.qualities.length === 0 && <p className="text-sm text-mist">No qualities yet.</p>}
          <ul className="flex flex-col gap-2">
            {d.qualities.map((q, i) => {
              const known = quality(q.name);
              return (
                <li key={i} className="flex flex-col gap-1 rounded-md border border-ash/60 p-2 sm:flex-row sm:items-center sm:gap-3">
                  <span className="min-w-0 flex-1 text-sm">
                    {q.name}
                    {known && known.kind !== "standard" && <span className="ml-1 text-xs text-gold">{KIND_HEADINGS[known.kind]}</span>}
                    {known && !known.counts && known.kind !== "elysium" && <span className="ml-1 text-xs text-mist">doesn't count</span>}
                    {!known && <span className="ml-1 text-xs text-mist">no longer offered here</span>}
                    {known && <span className="block text-xs text-mist">{known.text}</span>}
                  </span>
                  {(known?.detail || q.detail) && (
                    <Input
                      aria-label={`${q.name}: ${known?.detail || "detail"}`}
                      placeholder={known?.detail || "Detail"}
                      value={q.detail}
                      className="sm:w-56"
                      onChange={(e) => set({ qualities: d.qualities.map((x, n) => (n === i ? { ...x, detail: e.target.value } : x)) })}
                    />
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    className="min-h-8 self-end px-2 sm:self-auto"
                    aria-label={`Remove ${q.name}`}
                    onClick={() => set({ qualities: d.qualities.filter((_, n) => n !== i) })}
                  >
                    Remove
                  </Button>
                </li>
              );
            })}
          </ul>
          <Field label="Add a quality">
            <Select
              value=""
              onChange={(e) => {
                if (e.target.value) set({ qualities: [...d.qualities, { name: e.target.value, detail: "" }] });
              }}
            >
              <option value="">Choose…</option>
              {["standard", "iconic", "supernatural", "elysium"].map((kind) => (
                <optgroup key={kind} label={KIND_HEADINGS[kind]}>
                  {catalogue.qualities
                    .filter((q) => q.kind === kind)
                    .map((q) => (
                      <option key={q.name} value={q.name}>
                        {q.name}
                        {q.house ? " ★" : ""}
                        {q.min_rating ? ` (${q.min_rating}+)` : ""}
                      </option>
                    ))}
                </optgroup>
              ))}
            </Select>
          </Field>
        </fieldset>
      )}

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 font-sans text-xs tracking-wide text-mist uppercase">Negative qualities</legend>
        {d.negatives.map((n, i) => {
          const known = catalogue.negatives.find((x) => x.name === n.name);
          const most = known?.raised_by && d.qualities.some((q) => q.name === known.raised_by) ? 4 : 3;
          const change = (c: Partial<Negative>) => set({ negatives: d.negatives.map((x, m) => (m === i ? { ...x, ...c } : x)) });
          return (
            <div key={i} className="grid gap-2 rounded-md border border-ash/60 p-2 sm:grid-cols-[1fr_auto_auto_1fr_auto] sm:items-center">
              <Select aria-label="Negative quality" value={n.name} onChange={(e) => change({ name: e.target.value })}>
                {catalogue.negatives.map((x) => (
                  <option key={x.name} value={x.name}>
                    {x.name}
                  </option>
                ))}
              </Select>
              <Select aria-label={`${n.name} level`} value={n.level} className="w-20" onChange={(e) => change({ level: Number(e.target.value) })}>
                {Array.from({ length: most }, (_, k) => k + 1).map((k) => (
                  <option key={k} value={k}>
                    ×{k}
                  </option>
                ))}
              </Select>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={n.secret} onChange={(e) => change({ secret: e.target.checked })} />
                Secret from the controller
              </label>
              <Input aria-label={`Who is behind ${n.name}`} placeholder="Who is behind it" value={n.by} onChange={(e) => change({ by: e.target.value })} />
              <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove ${n.name}`} onClick={() => set({ negatives: d.negatives.filter((_, m) => m !== i) })}>
                Remove
              </Button>
              {known && <p className="text-xs text-mist sm:col-span-5">{known.levels[Math.min(n.level, 3) - 1]}</p>}
            </div>
          );
        })}
        <div>
          <Button
            type="button"
            variant="secondary"
            disabled={d.negatives.length >= catalogue.negatives.length}
            onClick={() => {
              const next = catalogue.negatives.find((x) => !d.negatives.some((n) => n.name === x.name));
              if (next) set({ negatives: [...d.negatives, { name: next.name, level: 1, secret: false, by: "" }] });
            }}
          >
            Add a negative quality
          </Button>
        </div>
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 font-sans text-xs tracking-wide text-mist uppercase">Control</legend>
        <Field label="Control">
          <Select value={d.held} onChange={(e) => set({ held: e.target.value as Held })}>
            <option value="controlled">Controlled</option>
            <option value="none">Uncontrolled</option>
            <option value="uncontrollable">Uncontrollable</option>
          </Select>
        </Field>
        {d.held === "controlled" && (
          <>
            <Field label="Controller" hint="A character in the troupe, or the name of an NPC.">
              <WhoPicker characters={characters} who={d.controller.who} name={d.controller.name} onChange={(who, name) => set({ controller: { who, name } })} />
            </Field>
            <PersonField label="Joint control (optional)" characters={characters} value={d.joint} onChange={(joint) => set({ joint })} />
          </>
        )}
        <PersonField label="Heir or ranking officer (optional)" characters={characters} value={d.heir} onChange={(heir) => set({ heir })} />
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-2 font-sans text-xs tracking-wide text-mist uppercase">Haven and Elysium</legend>
        <Field label="A Haven of" hint={d.kind === "haven" ? "Whose Haven background this is." : "Mark it as a character's Haven: it can't be targeted, and doesn't count toward the control limit."}>
          <Select value={d.haven_of_id} onChange={(e) => set({ haven_of_id: e.target.value })}>
            <option value="">{d.kind === "haven" ? "Choose…" : "Nobody's"}</option>
            {havens.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} (Haven {c.haven})
              </option>
            ))}
          </Select>
        </Field>
        {d.haven_of_id && (
          <fieldset className="text-sm">
            <legend className="mb-1 text-mist">
              Advantages{owner ? `: one for each dot of Haven (${owner.haven})` : ""}
            </legend>
            <div className="grid grid-cols-2 gap-1">
              {catalogue.haven_advantages.map((a) => (
                <label key={a.name} className="flex items-center gap-2" title={a.text}>
                  <input
                    type="checkbox"
                    checked={d.haven_advantages.includes(a.name)}
                    onChange={(e) =>
                      set({ haven_advantages: e.target.checked ? [...d.haven_advantages, a.name] : d.haven_advantages.filter((x) => x !== a.name) })
                    }
                  />
                  {a.name}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {d.kind !== "haven" && (
          <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row sm:items-end sm:gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={d.elysium} onChange={(e) => set({ elysium: e.target.checked })} />
              Elysium
            </label>
            {d.elysium && (
              <Field label="Unviolated since (year)" hint={`One Elysium quality, a second after a decade, one more each century (p. ${catalogue.pages.elysium_page ?? "131"}).`}>
                <Input type="number" inputMode="numeric" value={d.elysium_since} className="w-32" onChange={(e) => set({ elysium_since: e.target.value })} />
              </Field>
            )}
          </div>
        )}
      </fieldset>

      <Field label="Notes for staff">
        <Textarea value={d.notes} onChange={(e) => set({ notes: e.target.value })} />
      </Field>

      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {location ? "Save changes" : "Add location"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

/** An optional person: a character, or a name, with a way to clear it. */
function PersonField({
  label,
  characters,
  value,
  onChange,
}: {
  label: string;
  characters: { id: string; name: string; kind: string; in_troupe: boolean }[];
  value: Who;
  onChange: (value: Who) => void;
}) {
  // Clearing starts the picker afresh.
  const [round, setRound] = useState(0);
  return (
    <div className="flex items-end gap-2">
      <div className="min-w-0 flex-1">
        <Field label={label}>
          <WhoPicker key={round} characters={characters} who={value.who} name={value.name} onChange={(who, name) => onChange({ who, name })} />
        </Field>
      </div>
      {value.who && (
        <Button
          type="button"
          variant="ghost"
          className="min-h-10 px-2"
          aria-label={`Clear ${label.replace(" (optional)", "").toLowerCase()}`}
          onClick={() => {
            onChange(NOBODY);
            setRound(round + 1);
          }}
        >
          Clear
        </Button>
      )}
    </div>
  );
}

export function Warnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <Notice>
      Saved, but: {warnings.join(" ")}
    </Notice>
  );
}
