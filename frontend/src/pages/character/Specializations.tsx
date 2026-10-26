import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, SheetTraitOut } from "../../api/types";
import { Button, ErrorText, Input } from "../../components/ui";
import { useAction } from "../../hooks";
import { FIELD_PLACEHOLDER, fieldNeeded } from "./fields";

const CUSTOM = "Custom";

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
  const [open, setOpen] = useState(false);
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
  const room = held.length < Math.max(kind.parent_rating, 1);
  const pick = (option: string) => {
    // A troupe's options and free text are both stored as Custom with the text.
    change.mutate(kind.from_troupe ? { name: CUSTOM, detail: option, rating: 1 } : { name: option, detail: "", rating: 1 });
    setOpen(false);
  };
  const missing = held.length < kind.parent_rating;

  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs">
      <span className="flex flex-wrap items-center gap-1.5">
        <span className={missing ? "text-gold" : "text-mist"}>
          {kind.name} {held.length}/{kind.parent_rating}
        </span>
        {held.map((h) => (
          <span key={`${h.name}/${h.detail}`} className="inline-flex items-center gap-1 rounded border border-ash px-1.5 text-parchment">
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
        {editable && room && (
          <button
            aria-label={`Add to ${kind.name}`}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className={`rounded border px-1.5 ${open ? "border-gold text-gold" : "border-dashed border-mist/60 text-mist hover:border-gold hover:text-gold"}`}
          >
            {open ? "Close" : "+ Add"}
          </button>
        )}
      </span>
      {open && (
        <div className="mt-1.5 flex flex-col gap-1.5 rounded border border-ash bg-night/50 p-2">
          <div className="flex flex-wrap gap-1">
            {options.map((o) => (
              <button
                key={o}
                disabled={change.isPending}
                onClick={() => pick(o)}
                className="rounded border border-ash px-1.5 py-0.5 text-parchment hover:border-gold hover:text-gold"
              >
                {o}
              </button>
            ))}
            {options.length === 0 && !kind.custom && <span className="text-mist">Nothing left to choose.</span>}
          </div>
          {kind.custom && (
            <form
              className="flex items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                if (!text.trim()) return;
                change.mutate({ name: CUSTOM, detail: text.trim(), rating: 1 });
                setText("");
                setOpen(false);
              }}
            >
              <Input aria-label={`Name a ${kind.name}`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Or name your own" className="min-h-7 w-44 py-0.5 text-xs" />
              <Button type="submit" variant="secondary" className="min-h-7 px-2 py-0.5 text-xs" disabled={!text.trim() || change.isPending}>
                Add
              </Button>
            </form>
          )}
        </div>
      )}
      <ErrorText error={change.error} />
    </div>
  );
}

/** A Crafts, Performance or Science held without its field: set one. */
export function SetField({ character, trait }: { character: CharacterOut; trait: Pick<SheetTraitOut, "category" | "name"> }) {
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
    <div className="-mt-0.5 mb-1 ml-3 flex flex-wrap items-center gap-1.5 border-l border-blood/60 pl-3 text-xs">
      <span className="text-blood-bright">{fieldNeeded(trait.name)}:</span>
      <Input aria-label={`${trait.name} field`} value={field} onChange={(e) => setField(e.target.value)} placeholder={FIELD_PLACEHOLDER} className="min-h-8 w-40 py-1 text-xs" />
      <Button variant="secondary" className="min-h-8 px-2 py-1 text-xs" disabled={!field.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
        Set
      </Button>
      <ErrorText error={save.error} />
    </div>
  );
}
