import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { FORM_NAMES, type NpcForm, type NpcKind, groupedKinds, kindPages, resourceText } from "./npcKinds";

type Custom = { name: string; nature: "mortal" | "supernatural"; resource: { name: string; size: number; per_turn: number; regains: string } };
const NEW_CUSTOM: Custom = { name: "", nature: "supernatural", resource: { name: "Blood", size: 10, per_turn: 1, regains: "" } };

/**
 * The fast way to make an NPC, on the troupe's Characters list when it shows NPCs:
 * its name, kind and form. A sheeted one goes to its quick build or to step-by-step
 * creation; a Stock NPC has no sheet to go to, so it joins the list.
 */
export function NewNpc({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const toast = useToast();
  const path = { params: { path: { troupe_id: troupeId } } };
  const kinds = useQuery({ queryKey: ["npc-kinds"], queryFn: () => unwrap(api.GET("/api/npc-kinds")), staleTime: Infinity });
  const [name, setName] = useState("");
  const [kindKey, setKindKey] = useState("vampire");
  const [form, setForm] = useState<NpcForm>("sheeted");
  const [rating, setRating] = useState(1);
  const [custom, setCustom] = useState<Custom>(NEW_CUSTOM);
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
    toast({ message: `${npc.name} joined the list.` });
  });
  const ready = !!name && !(kind?.custom && !custom.name) && !create.isPending;

  return (
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
