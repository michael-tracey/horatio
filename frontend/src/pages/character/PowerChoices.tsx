import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { PowerChoices as Choices } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";

function usePowerChoices(characterId: string) {
  return useQuery({
    queryKey: ["power-choices", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/power-choices", { params: { path: { character_id: characterId } } })),
  });
}

const shown = (c: Choices["choices"][number]) => c.value || c.default || "none";

/** One power's choices: what was chosen (or each default), and a form to choose while that is allowed. */
function PowerRow({ characterId, power }: { characterId: string; power: Choices }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(power.choices.map((c) => [c.key, c.value])));
  const save = useAction(async () => {
    const data = await unwrap(
      api.PUT("/api/characters/{character_id}/power-choices", {
        params: { path: { character_id: characterId } },
        body: { discipline: power.discipline, power: power.power, values },
      }),
    );
    client.setQueryData(["power-choices", characterId], data);
    await client.invalidateQueries({ queryKey: ["play", characterId] });
    setEditing(false);
  });
  return (
    <div className="mt-1 rounded-md border border-ash/70 px-2 py-1.5 text-xs" aria-label={`${power.power} choices`}>
      <p>
        <span className="text-mist">{power.power}: </span>
        {power.choices.map((c) => `${c.label.toLowerCase()} ${shown(c)}`).join(" · ")}
      </p>
      {!editing && (
        <p className="text-mist">
          {!power.chosen && "Chosen when you buy it, and fixed after (p. 155). "}
          {power.chosen && !power.can_change && "Fixed once chosen; your storytellers can change it."}
          {power.can_change && (
            <button type="button" className="underline hover:text-parchment" onClick={() => setEditing(true)}>
              {power.chosen ? "change" : "choose"}
            </button>
          )}
        </p>
      )}
      {editing && (
        <form
          className="mt-1 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          {power.choices.map((c) => (
            <label key={c.key} className="flex flex-col gap-1 text-mist">
              {c.label}
              {c.options.length > 0 ? (
                <Select value={values[c.key] ?? ""} onChange={(e) => setValues({ ...values, [c.key]: e.target.value })}>
                  <option value="">None</option>
                  {c.options.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </Select>
              ) : (
                <Input value={values[c.key] ?? ""} maxLength={40} placeholder={c.default} onChange={(e) => setValues({ ...values, [c.key]: e.target.value })} className="w-32" />
              )}
            </label>
          ))}
          <Button type="submit" variant="secondary" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      )}
    </div>
  );
}

/**
 * What was chosen when buying this discipline's powers (issue #200), such as
 * Shape of the Beast's animals and fight form template, under its row on the
 * sheet. Nothing shows for a discipline without such a power.
 */
export function PowerChoices({ characterId, discipline }: { characterId: string; discipline: string }) {
  const choices = usePowerChoices(characterId);
  const mine = (choices.data ?? []).filter((c) => c.discipline === discipline);
  if (mine.length === 0) return null;
  return (
    <>
      {mine.map((p) => (
        <PowerRow key={p.power} characterId={characterId} power={p} />
      ))}
    </>
  );
}
