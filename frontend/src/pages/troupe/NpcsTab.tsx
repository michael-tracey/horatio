import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { FORM_NAMES, type NpcFilter, type NpcForm, type NpcKind, filterNpcs, groupedKinds, kindPages, kindsIn, resourceText } from "./npcKinds";

type Custom = { name: string; nature: "mortal" | "supernatural"; resource: { name: string; size: number; per_turn: number; regains: string } };
const NEW_CUSTOM: Custom = { name: "", nature: "supernatural", resource: { name: "Blood", size: 10, per_turn: 1, regains: "" } };

/** The troupe's NPCs, with their kind and form, each sheeted one with a way into
 * its Play View, badges to print for them, and the fast way to make another. */
export function NpcsTab({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const path = { params: { path: { troupe_id: troupeId } } };
  const npcs = useQuery({ queryKey: ["npcs", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/npcs", path)) });
  const kinds = useQuery({ queryKey: ["npc-kinds"], queryFn: () => unwrap(api.GET("/api/npc-kinds")), staleTime: Infinity });
  const [name, setName] = useState("");
  const [kindKey, setKindKey] = useState("vampire");
  const [form, setForm] = useState<NpcForm>("sheeted");
  const [rating, setRating] = useState(1);
  const [custom, setCustom] = useState<Custom>(NEW_CUSTOM);
  const [filter, setFilter] = useState<NpcFilter>({ kind: "", form: "" });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const kind = kinds.data?.find((k) => k.key === kindKey);
  const create = useAction(async (wizard: boolean) => {
    const body = {
      name,
      splat: "vampire",
      wizard,
      npc_kind: kindKey,
      npc_form: form,
      custom_kind: kind?.custom ? custom : null,
      stock: form === "stock" ? { rating, specializations: [], notes: "" } : null,
    };
    const npc = await unwrap(api.POST("/api/troupes/{troupe_id}/npcs", { ...path, body }));
    if (form === "sheeted") {
      navigate(`/characters/${npc.id}${wizard ? "/create" : ""}`);
      return;
    }
    // A Stock NPC has no sheet to go to: it joins the list here.
    setName("");
    await queryClient.invalidateQueries({ queryKey: ["npcs", troupeId] });
  });
  const listOnWhosWho = useAction(({ id, listed }: { id: string; listed: boolean }) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/npcs/{character_id}/whos-who", { params: { path: { troupe_id: troupeId, character_id: id } }, body: { listed } })),
  );
  const ready = !!name && !(kind?.custom && !custom.name) && !create.isPending;
  const all = npcs.data ?? [];
  const shown = filterNpcs(all, filter);
  const ticked = all.filter((n) => selected.has(n.id));
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (!next.delete(id)) next.add(id);
    setSelected(next);
  };
  // The same badge sheets as the Characters tab's, opened in a new tab so what is ticked stays.
  const badges = (ids: string[]) => window.open(`/print/troupes/${troupeId}/badges?characters=${ids.join(",")}`, "_blank", "noopener");

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <Card title="NPCs">
        {all.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-mist">Game badges:</span>
            <Button variant="secondary" disabled={!ticked.length} onClick={() => badges(ticked.map((n) => n.id))}>
              Badges for selected ({ticked.length})
            </Button>
            <Button variant="secondary" onClick={() => badges(all.map((n) => n.id))}>
              Badges for all NPCs
            </Button>
          </div>
        )}
        {all.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-3">
            <Select aria-label="Show kind" className="w-auto" value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value })}>
              <option value="">All kinds</option>
              {kindsIn(all).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </Select>
            <Select aria-label="Show form" className="w-auto" value={filter.form} onChange={(e) => setFilter({ ...filter, form: e.target.value as NpcFilter["form"] })}>
              <option value="">Sheeted and Stock</option>
              <option value="sheeted">Sheeted only</option>
              <option value="stock">Stock only</option>
            </Select>
          </div>
        )}
        {npcs.isPending ? (
          <Loading />
        ) : shown.length ? (
          <ul className="divide-y divide-ash">
            {shown.map((n) => (
              <li key={n.id} aria-label={n.name} className="flex flex-wrap items-center gap-3 py-2">
                <input type="checkbox" aria-label={`Select ${n.name}`} checked={selected.has(n.id)} onChange={() => toggle(n.id)} />
                {n.npc_form === "stock" ? (
                  // Its builder, in place of a sheet (issue #215).
                  <Link to={`/troupes/${troupeId}/npcs/${n.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:text-gold">
                    <Avatar name={n.name} picture={n.picture} clan={n.clan} />
                    <span className="truncate">{n.name}</span>
                  </Link>
                ) : (
                  <Link to={`/characters/${n.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:text-gold">
                    <Avatar name={n.name} picture={n.picture} clan={n.clan} />
                    <span className="truncate">{n.name}</span>
                  </Link>
                )}
                <span className="flex items-center gap-1">
                  <Badge tone="gold">{n.npc_kind_name ?? n.splat}</Badge>
                  <Badge>{FORM_NAMES[(n.npc_form ?? "sheeted") as NpcForm]}</Badge>
                  {n.stock_rating != null && <Badge>Rating {n.stock_rating}</Badge>}
                </span>
                <label className="flex items-center gap-1.5 text-xs text-mist" title="Titled NPCs are on the Who's Who anyway.">
                  <input
                    type="checkbox"
                    aria-label={`List ${n.name} on the Who's Who`}
                    checked={n.on_whos_who}
                    disabled={listOnWhosWho.isPending}
                    onChange={(e) => listOnWhosWho.mutate({ id: n.id, listed: e.target.checked })}
                  />
                  Who’s Who
                </label>
                <Link
                  to={`/play/characters/${n.id}`}
                  aria-label={`Play ${n.name}`}
                  className="inline-flex min-h-9 items-center rounded-md bg-blood px-3 text-sm font-medium text-parchment hover:bg-blood-bright"
                >
                  Play
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{all.length ? "No NPCs of that kind." : "No NPCs yet."}</Empty>
        )}
        <ErrorText error={npcs.error} />
        <ErrorText error={listOnWhosWho.error} />
        {all.length > 0 && <p className="mt-3 text-xs text-mist">NPCs with a title here are on the Who’s Who. Tick Who’s Who to list one without.</p>}
      </Card>
      <Card title="New NPC">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(false);
          }}
        >
          <Field label="Name">
            <Input required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Kind" hint={kind && <KindSummary kind={kind} />}>
            <Select value={kindKey} onChange={(e) => setKindKey(e.target.value)}>
              {groupedKinds(kinds.data ?? []).map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.kinds.map((k) => (
                    <option key={k.key} value={k.key}>
                      {k.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          {kind?.custom && <CustomKindFields custom={custom} onChange={setCustom} />}
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-mist">Form</span>
            <span role="radiogroup" aria-label="Form" className="inline-flex self-start overflow-hidden rounded-md border border-ash">
              {(["sheeted", "stock"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  role="radio"
                  aria-checked={form === f}
                  onClick={() => setForm(f)}
                  className={`min-h-9 px-3 text-sm ${form === f ? "bg-gold/20 text-gold" : "text-mist hover:text-parchment"} [&+&]:border-l [&+&]:border-ash`}
                >
                  {FORM_NAMES[f]}
                </button>
              ))}
            </span>
          </div>
          {form === "stock" && (
            <Field label="Rating" hint={`1 to ${kind?.rating_max ?? 5}: its test pool is twice this (p. 489).`}>
              <Input type="number" min={1} max={kind?.rating_max ?? 5} value={rating} onChange={(e) => setRating(Number(e.target.value))} />
            </Field>
          )}
          <ErrorText error={create.error} />
          {form === "sheeted" ? (
            <>
              <Button type="submit" disabled={!ready}>
                Quick build
              </Button>
              <Button type="button" variant="secondary" disabled={!ready} onClick={() => create.mutate(true)}>
                Use step-by-step creation
              </Button>
              <p className="text-xs text-mist">Quick build sets ratings directly, with a running tally of what the NPC is worth.</p>
            </>
          ) : (
            <>
              <Button type="submit" disabled={!ready}>
                Make Stock NPC
              </Button>
              <p className="text-xs text-mist">A Stock NPC has no sheet: only a rating and a few specializations (pp. 489–490).</p>
            </>
          )}
        </form>
      </Card>
    </div>
  );
}

/** What a kind is, in a line: mortal or not, its resource, and its pages. */
function KindSummary({ kind }: { kind: NpcKind }) {
  if (kind.custom) return <>Name it, and set whether it is mortal and what it spends.</>;
  const nature = { mortal: "Mortal", partly_mortal: "Partly mortal", supernatural: "Supernatural" }[kind.nature];
  return (
    <>
      {nature} · {resourceText(kind.resource)} · {kindPages(kind)}
    </>
  );
}

/** A custom kind's name, whether it is mortal, and what it spends. */
function CustomKindFields({ custom, onChange }: { custom: Custom; onChange: (c: Custom) => void }) {
  const resource = (changes: Partial<Custom["resource"]>) => onChange({ ...custom, resource: { ...custom.resource, ...changes } });
  return (
    <fieldset className="flex flex-col gap-3 rounded-md border border-ash p-3">
      <legend className="px-1 text-sm text-mist">Custom kind</legend>
      <Field label="What it is">
        <Input required placeholder="Demon, ghost, angel…" value={custom.name} onChange={(e) => onChange({ ...custom, name: e.target.value })} />
      </Field>
      <Field label="Mortal or supernatural">
        <Select value={custom.nature} onChange={(e) => onChange({ ...custom, nature: e.target.value as Custom["nature"] })}>
          <option value="supernatural">Supernatural</option>
          <option value="mortal">Mortal: skill specialisations only</option>
        </Select>
      </Field>
      <div className="grid grid-cols-3 gap-2">
        <Field label="It spends">
          <Input required value={custom.resource.name} onChange={(e) => resource({ name: e.target.value })} />
        </Field>
        <Field label="Pool">
          <Input type="number" min={1} max={50} value={custom.resource.size} onChange={(e) => resource({ size: Number(e.target.value) })} />
        </Field>
        <Field label="A turn">
          <Input type="number" min={0} max={10} value={custom.resource.per_turn} onChange={(e) => resource({ per_turn: Number(e.target.value) })} />
        </Field>
      </div>
    </fieldset>
  );
}
