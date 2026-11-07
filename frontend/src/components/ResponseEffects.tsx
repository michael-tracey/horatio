import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { ResponseEffectsOut, WorkItemOut } from "../api/types";
import { useAction } from "../hooks";
import { Button, ErrorText, Field, Select } from "./ui";

type Kind = "hungry_dead" | "indirect_attack" | "crafts" | "performance" | "overtaxed" | "recovery";

/** The effects staff can apply, as the list offers them; effects on another character need one chosen. */
export function effectChoices(effects: ResponseEffectsOut): { kind: Kind; label: string; aimed: boolean }[] {
  const cost = effects.indirect_cost;
  return [
    { kind: "hungry_dead", label: "Call of the Hungry Dead: another character loses 1 action, once (p. 181)", aimed: true },
    ...(cost ? [{ kind: "indirect_attack" as const, label: `Indirect influence attack: another character loses ${cost} ${cost === 1 ? "action" : "actions"} (p. 512)`, aimed: true }] : []),
    { kind: "crafts", label: "Crafts: Resources +1 this month (p. 93)", aimed: false },
    { kind: "performance", label: "Performance: Fame +1 this month (p. 96)", aimed: false },
    { kind: "overtaxed", label: "Overtaxed Resources: −2 for six games or three months (p. 103)", aimed: false },
    ...(effects.recovering && !effects.halved ? [{ kind: "recovery" as const, label: "Recovering from overtaxing: halve the wait (p. 103)", aimed: false }] : []),
  ];
}

/**
 * What a response does besides its words (backend: horatio.downtime_effects): actions
 * another character loses, a background raised or lowered for a while. Folded away
 * until staff open it, and only for storytellers and assistants.
 */
export function ResponseEffects({ item }: { item: WorkItemOut }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind | "">("");
  const [target, setTarget] = useState("");
  const client = useQueryClient();
  const key = ["response-effects", item.id];
  const path = { params: { path: { response_id: item.id } } };
  const effects = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/responses/{response_id}/effects", path)), enabled: open });
  const apply = useAction(async () => {
    const found = await unwrap(api.POST("/api/responses/{response_id}/effects", { ...path, body: { kind: kind as Kind, character_id: target || null } }));
    client.setQueryData(key, found);
    setKind("");
    setTarget("");
  });
  const remove = useAction(async (id: string) => {
    client.setQueryData(key, await unwrap(api.DELETE("/api/responses/{response_id}/effects/{effect_id}", { params: { path: { response_id: item.id, effect_id: id } } })));
  });

  if (!open)
    return (
      <Button variant="ghost" className="self-start px-0" aria-expanded={false} onClick={() => setOpen(true)}>
        Effects on allowances and backgrounds…
      </Button>
    );
  const data = effects.data;
  const choices = data ? effectChoices(data) : [];
  const chosen = choices.find((c) => c.kind === kind);
  return (
    <section className="flex flex-col gap-2 border-t border-ash pt-2" aria-label={`Effects of ${item.character_name}'s action`}>
      <Button variant="ghost" className="self-start px-0" aria-expanded onClick={() => setOpen(false)}>
        Effects on allowances and backgrounds
      </Button>
      <ErrorText error={effects.error} />
      {data && data.applied.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {data.applied.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2">
              <span className="text-gold">{a.text}</span>
              <Button variant="ghost" className="min-h-8 px-2" aria-label={`Take back ${a.text}`} disabled={remove.isPending} onClick={() => remove.mutate(a.id)}>
                Take back
              </Button>
            </li>
          ))}
        </ul>
      )}
      {data && (
        <form
          className="grid gap-2 sm:grid-cols-[2fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            apply.mutate(undefined);
          }}
        >
          <Field label="Effect">
            <Select value={kind} onChange={(e) => setKind(e.target.value as Kind | "")}>
              <option value="">Choose…</option>
              {choices.map((c) => (
                <option key={c.kind} value={c.kind}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Field>
          {chosen?.aimed ? (
            <Field label="On">
              <Select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Choose…</option>
                {data.targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <span className="text-xs text-mist sm:pb-2">{chosen ? `On ${item.character_name}` : ""}</span>
          )}
          <Button type="submit" variant="secondary" disabled={!chosen || (chosen.aimed && !target) || apply.isPending}>
            Apply
          </Button>
        </form>
      )}
      <ErrorText error={apply.error ?? remove.error} />
    </section>
  );
}
