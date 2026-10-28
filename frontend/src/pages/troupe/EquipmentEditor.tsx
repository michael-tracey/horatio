import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { EquipmentItemOut, EquipmentOut, EquipmentHolderOut, TroupeTemplateOut } from "../../api/types";
import { Button, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { GRADE_NAMES, NEW_ITEM, body, factsText, fromItem, fromTemplate, qualityChoices, qualityOf, type Draft, type Grade, type Kind } from "./equipment";

/** The book's rules for a splat's equipment: kinds, grades, qualities and templates. */
export function useEquipmentRules(splat: string) {
  return useQuery({
    queryKey: ["equipment-rules", splat],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}/equipment", { params: { path: { splat } } })),
    staleTime: 10 * 60_000,
  });
}

/** The troupe's own templates. */
export function useTroupeTemplates(troupeId: string) {
  return useQuery({
    queryKey: ["equipment-templates", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/equipment/templates", { params: { path: { troupe_id: troupeId } } })),
  });
}

/**
 * Give an item to one of the troupe's home characters, or change one it holds:
 * from a template or by hand, with its facts and any rule it breaks shown as it
 * is built. A special item takes any number of qualities and effects of the
 * troupe's own.
 */
export function EquipmentEditor({
  troupeId,
  troupeName,
  holders,
  holder: fixedHolder,
  item,
  onDone,
}: {
  troupeId: string;
  troupeName: string;
  /** The characters it can go to: the troupe's home characters. */
  holders: EquipmentHolderOut[];
  /** Given to this character, not chosen. */
  holder?: EquipmentHolderOut;
  /** Changing this item, rather than giving a new one. */
  item?: EquipmentItemOut;
  onDone: (name: string) => void;
}) {
  const [holderId, setHolderId] = useState(fixedHolder?.id ?? item?.character_id ?? "");
  const holder = fixedHolder ?? holders.find((h) => h.id === holderId);
  const splat = holder?.splat ?? "vampire";
  const rules = useEquipmentRules(splat);
  const templates = useTroupeTemplates(troupeId);
  const [draft, setDraft] = useState<Draft>(item ? fromItem(item) : NEW_ITEM);
  const [template, setTemplate] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [savedTemplate, setSavedTemplate] = useState<string | null>(null);
  const set = (change: Partial<Draft>) => setDraft({ ...draft, ...change });

  const checked = body(draft);
  const check = useQuery({
    queryKey: ["equipment-check", splat, checked.kind, checked.grade, checked.qualities, checked.crafted, checked.archaic],
    queryFn: () =>
      unwrap(
        api.POST("/api/rules/{splat}/equipment/check", {
          params: { path: { splat } },
          body: { kind: checked.kind, grade: checked.grade, qualities: checked.qualities, crafted: checked.crafted, archaic: checked.archaic },
        }),
      ),
    placeholderData: (previous) => previous,
  });

  const save = useAction(async () => {
    if (item) {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/equipment/{item_id}", {
          params: { path: { troupe_id: troupeId, item_id: item.id } },
          body: { ...checked, reason },
        }),
      );
    } else {
      await unwrap(
        api.POST("/api/troupes/{troupe_id}/equipment", {
          params: { path: { troupe_id: troupeId } },
          body: { ...checked, character_id: holderId, template },
        }),
      );
    }
    onDone(draft.name.trim());
  });
  const keep = useAction(async () => {
    const { staff_note: _, ...fields } = checked;
    const saved = await unwrap(api.POST("/api/troupes/{troupe_id}/equipment/templates", { params: { path: { troupe_id: troupeId } }, body: { ...fields, splat } }));
    setSavedTemplate(saved.name);
  });

  if (rules.isPending) return <Loading />;
  if (rules.error) return <ErrorText error={rules.error} />;
  const book = rules.data;
  const own = templates.data ?? [];
  const choices = qualityChoices(book, draft.kind, draft.qualities);
  const problems = check.data?.problems ?? [];
  const label = item ? `Change ${item.name}` : "Give equipment";

  const startFrom = (value: string) => {
    const at = value.indexOf(":");
    const source = value.slice(0, at);
    const name = value.slice(at + 1);
    const found: EquipmentOut["templates"][number] | TroupeTemplateOut | undefined =
      source === "troupe" ? own.find((t) => t.id === name) : book.templates.find((t) => t.name === name);
    if (!found) return;
    setDraft({ ...fromTemplate(found), staff_note: draft.staff_note });
    setTemplate(found.name);
  };

  return (
    <form
      aria-label={label}
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {!item && !fixedHolder && (
        <Field label="Character">
          <Select value={holderId} onChange={(e) => setHolderId(e.target.value)}>
            <option value="">Choose…</option>
            {holders.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
                {h.kind === "npc" ? " (NPC)" : h.player_name ? ` (${h.player_name})` : ""}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {!item && (
        <Field label="Start from" hint="A template fills in the item, which you can then rename and adjust.">
          <Select value="" onChange={(e) => startFrom(e.target.value)}>
            <option value="">{template ? `${template} (change…)` : "Nothing: build it by hand"}</option>
            {own.length > 0 && (
              <optgroup label={`${troupeName}'s templates`}>
                {own.map((t) => (
                  <option key={t.id} value={`troupe:${t.id}`}>
                    {t.name}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label="The book's (MET: VTM pp. 521–524)">
              {book.templates.map((t) => (
                <option key={t.name} value={`book:${t.name}`}>
                  {t.name}
                </option>
              ))}
            </optgroup>
          </Select>
        </Field>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Name">
          <Input value={draft.name} onChange={(e) => set({ name: e.target.value })} placeholder="Grandfather's revolver" />
        </Field>
        <Field label="Kind">
          <Select value={draft.kind} onChange={(e) => set({ kind: e.target.value as Kind, qualities: [] })}>
            {book.kinds.map((k) => (
              <option key={k.key} value={k.key}>
                {k.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Grade">
          <Select value={draft.grade} onChange={(e) => set({ grade: e.target.value as Grade })}>
            {(Object.keys(GRADE_NAMES) as Grade[]).map((g) => (
              <option key={g} value={g}>
                {GRADE_NAMES[g]}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm text-mist">Qualities</legend>
        {draft.qualities.length === 0 && <p className="text-sm text-mist">None yet.</p>}
        <ul aria-label="Qualities chosen" className="flex flex-col gap-2">
          {draft.qualities.map((q, i) => {
            const quality = qualityOf(book, draft.kind, q.name);
            const takesDetail = quality?.needs_detail || !!quality?.detail_prompt;
            return (
              <li key={i} className="flex flex-wrap items-start gap-2 rounded-md border border-ash/60 p-2 text-sm">
                <div className="min-w-48 flex-1">
                  <span className="text-parchment">{q.name}</span>
                  {quality && (
                    <span className="block text-xs text-mist">
                      {quality.effect}
                      {quality.page && ` (p. ${quality.page})`}
                    </span>
                  )}
                  {takesDetail && (
                    <div className="mt-1">
                      <Field label={`${q.name} detail${quality?.needs_detail ? "" : " (optional)"}`} hint={quality?.detail_prompt ?? undefined}>
                        <Input
                          value={q.detail}
                          onChange={(e) => set({ qualities: draft.qualities.map((d, n) => (n === i ? { ...d, detail: e.target.value } : d)) })}
                        />
                      </Field>
                    </div>
                  )}
                </div>
                <Button type="button" variant="ghost" aria-label={`Remove ${q.name}`} onClick={() => set({ qualities: draft.qualities.filter((_, n) => n !== i) })}>
                  ×
                </Button>
              </li>
            );
          })}
        </ul>
        <Field label="Add a quality">
          <Select
            value=""
            onChange={(e) => {
              if (e.target.value) set({ qualities: [...draft.qualities, { name: e.target.value, detail: "" }] });
            }}
          >
            <option value="">Choose…</option>
            {choices.map((q) => (
              <option key={q.name} value={q.name}>
                {q.name}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.crafted} onChange={(e) => set({ crafted: e.target.checked })} />
          Crafted: its Artisan or Masterwork was added while crafting, and takes no slot
        </label>
        {draft.kind === "ranged" && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.archaic} onChange={(e) => set({ archaic: e.target.checked })} />
            Archaic (a bow or crossbow): may shoot with Athletics instead of Firearms, p. 279
          </label>
        )}
      </fieldset>

      {draft.grade === "special" && (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm text-mist">Special effects, the troupe's own</legend>
          {draft.effects.map((effect, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2">
              <div className="min-w-40 flex-1">
                <Field label={`Effect ${i + 1}`}>
                  <Input
                    value={effect.name}
                    placeholder="Drinks the Blood"
                    onChange={(e) => set({ effects: draft.effects.map((d, n) => (n === i ? { ...d, name: e.target.value } : d)) })}
                  />
                </Field>
              </div>
              <div className="min-w-60 flex-[2]">
                <Field label={`What effect ${i + 1} does`}>
                  <Input
                    value={effect.effect}
                    placeholder="Once a game, heal 1 normal damage when it draws blood"
                    onChange={(e) => set({ effects: draft.effects.map((d, n) => (n === i ? { ...d, effect: e.target.value } : d)) })}
                  />
                </Field>
              </div>
              <Button type="button" variant="ghost" aria-label={`Remove effect ${i + 1}`} onClick={() => set({ effects: draft.effects.filter((_, n) => n !== i) })}>
                ×
              </Button>
            </div>
          ))}
          <Button type="button" variant="secondary" className="self-start" onClick={() => set({ effects: [...draft.effects, { name: "", effect: "" }] })}>
            Add a special effect
          </Button>
        </fieldset>
      )}

      <div aria-live="polite" className="flex flex-col gap-1 rounded-md border border-ash/60 bg-night/40 p-2 text-sm">
        <p aria-label="What it is">{check.data ? factsText(check.data) || "No hands, damage or range: it isn't a weapon." : "…"}</p>
        {!!check.data?.aggravated_against.length && <p className="text-xs text-mist">Aggravated damage to {check.data.aggravated_against.join("; ")}.</p>}
        {problems.length > 0 && (
          <ul aria-label="Rules it breaks" className="list-inside list-disc text-blood-bright">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
      </div>

      <Field label="Description (optional)" hint="Where it came from, or what it looks like. Its holder's player sees it.">
        <Textarea rows={2} value={draft.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <Field label="Staff note (optional)" hint="Only staff see it.">
        <Textarea rows={2} value={draft.staff_note} onChange={(e) => set({ staff_note: e.target.value })} />
      </Field>
      {item && (
        <Field label="Why it changes" hint="Its holder's player is told, and it goes in the character's log.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      )}
      <ErrorText error={save.error ?? keep.error} />
      {savedTemplate && <Notice>Saved {savedTemplate} as one of {troupeName}'s templates.</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !draft.name.trim() || (!item && !holderId)}>
          {item ? "Save changes" : holder ? `Give to ${holder.name}` : "Give"}
        </Button>
        {!item && (
          <Button type="button" variant="secondary" disabled={keep.isPending || !draft.name.trim()} onClick={() => keep.mutate(undefined)}>
            Save as a template
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={() => onDone("")}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
