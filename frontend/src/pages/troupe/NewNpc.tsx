import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { FORM_NAMES, type NpcForm, type NpcKind, groupedKinds, kindPages, resourceText } from "./npcKinds";
import { GROUP_MAX } from "./stockNpcs";

type Custom = { name: string; nature: "mortal" | "supernatural"; resource: { name: string; size: number; per_turn: number; regains: string } };
const NEW_CUSTOM: Custom = { name: "", nature: "supernatural", resource: { name: "Blood", size: 10, per_turn: 1, regains: "" } };

/**
 * The fast way to make an NPC, on the troupe's Characters list when it shows NPCs:
 * its name, kind and form. A sheeted one goes to its quick build or to step-by-step
 * creation; a Stock NPC goes to its own page, for its specialisations and notes. A
 * Stock NPC can be a group of identical ones, played on one card (#1056).
 */
export function NewNpc({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const path = { params: { path: { troupe_id: troupeId } } };
  const kinds = useQuery({ queryKey: ["npc-kinds"], queryFn: () => unwrap(api.GET("/api/npc-kinds")), staleTime: Infinity });
  const [name, setName] = useState("");
  const [kindKey, setKindKey] = useState("vampire");
  const [form, setForm] = useState<NpcForm>("sheeted");
  const [rating, setRating] = useState(1);
  const [count, setCount] = useState(1);
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
      stock: form === "stock" ? { rating, count, specializations: [], notes: "" } : null,
    };
    const npc = await unwrap(api.POST("/api/troupes/{troupe_id}/npcs", { ...path, body }));
    // A sheeted NPC opens its sheet; a Stock NPC, which has none, opens its own page (#1040).
    navigate(form === "sheeted" ? `/characters/${npc.id}${wizard ? "/create" : ""}` : `/troupes/${troupeId}/npcs/${npc.id}`);
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
        <Select
          value={kindKey}
          onChange={(e) => {
            setKindKey(e.target.value);
            // A rating above the new kind's highest comes down to it.
            const max = kinds.data?.find((k) => k.key === e.target.value)?.rating_max;
            if (max) setRating((r) => Math.min(r, max));
          }}
        >
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Rating" hint={`1 to ${kind?.rating_max ?? 5}: its test pool is twice this (p. 489).`}>
            <Select value={rating} onChange={(e) => setRating(Number(e.target.value))}>
              {upTo(1, kind?.rating_max ?? 5).map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="How many" hint="More than 1 makes a group: one card, a health track each.">
            <Select value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {upTo(1, GROUP_MAX).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        </div>
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

/** The whole numbers from `first` to `last`, for a drop-down. */
function upTo(first: number, last: number): number[] {
  return Array.from({ length: last - first + 1 }, (_, i) => first + i);
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
          <Select value={custom.resource.size} onChange={(e) => resource({ size: Number(e.target.value) })}>
            {upTo(1, 50).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="A turn">
          <Select value={custom.resource.per_turn} onChange={(e) => resource({ per_turn: Number(e.target.value) })}>
            {upTo(0, 10).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
      </div>
    </fieldset>
  );
}
