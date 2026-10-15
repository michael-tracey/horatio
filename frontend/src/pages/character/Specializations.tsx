import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, SheetTraitOut } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";

const CUSTOM = "Custom";
const OTHER = "\u0000other";

export function useSpecializations(characterId: string) {
  return useQuery({
    queryKey: ["specializations", characterId],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/specializations", { params: { path: { character_id: characterId } } })),
  });
}

export type Kind = NonNullable<ReturnType<typeof useSpecializations>["data"]>[number];

/**
 * A skill or background's specialisations, under it on the sheet: what the
 * character has, and (if they can edit) a way to add another or remove one.
 * Options come from the troupe's list where it has one.
 */
export function SpecializationRow({ character, kind, editable }: { character: CharacterOut; kind: Kind; editable: boolean }) {
  const [choice, setChoice] = useState("");
  const [text, setText] = useState("");
  const change = useAction((body: { name: string; detail: string; rating: number }) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { category: kind.category, teacher: "", ...body },
      }),
    ),
  );
  const held = kind.held.map((h) => {
    const name = h.name ?? "";
    const detail = h.detail ?? "";
    return { name, detail, label: name === CUSTOM ? detail : detail ? `${name}: ${detail}` : name };
  });
  const heldLabels = new Set(held.map((h) => h.label));
  const options = kind.options.filter((o) => !heldLabels.has(o));
  const add = () => {
    if (choice === OTHER) change.mutate({ name: CUSTOM, detail: text.trim(), rating: 1 });
    else if (kind.from_troupe) change.mutate({ name: CUSTOM, detail: choice, rating: 1 });
    else change.mutate({ name: choice, detail: "", rating: 1 });
    setChoice("");
    setText("");
  };

  return (
    <li className="-mt-0.5 mb-1 ml-3 flex flex-col gap-1 border-l border-ash pl-3 text-xs">
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-mist">
          {kind.name} ({held.length} of {kind.parent_rating}):
        </span>
        {held.length === 0 && <span className="text-mist italic">none yet</span>}
        {held.map((h) => (
          <span key={`${h.name}/${h.detail}`} className="inline-flex items-center gap-1 rounded border border-ash px-1.5 py-0.5 text-parchment">
            {h.label}
            {editable && (
              <button
                aria-label={`Remove ${h.label}`}
                className="text-mist hover:text-blood-bright"
                onClick={() => change.mutate({ name: h.name, detail: h.detail, rating: 0 })}
              >
                ×
              </button>
            )}
          </span>
        ))}
      </span>
      {editable && held.length < Math.max(kind.parent_rating, 1) && (
        <span className="flex flex-wrap items-center gap-1.5">
          <Select aria-label={`Choose ${kind.name}`} value={choice} onChange={(e) => setChoice(e.target.value)} className="min-h-8 w-48 py-1 text-xs">
            <option value="">Add {kind.from_troupe ? "from the troupe's list" : "one"}…</option>
            {options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
            {kind.custom && <option value={OTHER}>Something else…</option>}
          </Select>
          {choice === OTHER && (
            <Input aria-label={`Name the ${kind.name}`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Name it" className="min-h-8 w-40 py-1 text-xs" />
          )}
          <Button
            aria-label={`Add to ${kind.name}`}
            variant="secondary"
            className="min-h-8 px-2 py-1 text-xs"
            disabled={!choice || (choice === OTHER && !text.trim()) || change.isPending}
            onClick={add}
          >
            Add
          </Button>
        </span>
      )}
      <ErrorText error={change.error} />
    </li>
  );
}

/** Skills bought once per field (MET: VTM p. 92). */
export const NEEDS_FIELD = new Set(["Crafts", "Performance", "Science"]);

/** A Crafts, Performance or Science held without its field: set one. */
export function SetField({ character, trait }: { character: CharacterOut; trait: SheetTraitOut }) {
  const [field, setField] = useState("");
  const save = useAction(() =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits/detail", {
        params: { path: { character_id: character.id } },
        body: { category: trait.category, name: trait.name, detail: field.trim() },
      }),
    ),
  );
  return (
    <li className="-mt-0.5 mb-1 ml-3 flex flex-wrap items-center gap-1.5 border-l border-blood/60 pl-3 text-xs">
      <span className="text-blood-bright">{trait.name} needs a field:</span>
      <Input aria-label={`${trait.name} field`} value={field} onChange={(e) => setField(e.target.value)} placeholder="Such as Singing" className="min-h-8 w-40 py-1 text-xs" />
      <Button variant="secondary" className="min-h-8 px-2 py-1 text-xs" disabled={!field.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
        Set
      </Button>
      <ErrorText error={save.error} />
    </li>
  );
}
