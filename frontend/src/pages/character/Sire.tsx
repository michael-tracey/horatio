import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, CharacterSireOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";

type Kind = "linked" | "named" | "none";

function kindOf(sire: CharacterSireOut): Kind {
  return sire.character_id ? "linked" : sire.name ? "named" : "none";
}

/**
 * Give the character its sire (#707): a vampire in its troupe, or someone known by
 * name and clan, or none. Its player gives it, or its troupe's storytellers. The
 * troupe's sire lines show it, unless it is kept from the players.
 */
export function CharacterSire({ character, sire, onDone }: { character: CharacterOut; sire: CharacterSireOut; onDone: () => void }) {
  const [kind, setKind] = useState<Kind>(kindOf(sire));
  const [linked, setLinked] = useState(sire.character_id ?? "");
  const [name, setName] = useState(sire.character_id ? "" : sire.name);
  const [clan, setClan] = useState(sire.character_id ? "" : sire.clan);
  const [secret, setSecret] = useState(sire.secret);
  const choices = useQuery({
    queryKey: ["sire-choices", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sire/choices", { params: { path: { character_id: character.id } } })),
  });
  const save = useAction(async () => {
    const body =
      kind === "linked"
        ? { character_id: linked || null, name: "", clan: "", secret }
        : kind === "named"
          ? { character_id: null, name, clan, secret }
          : { character_id: null, name: "", clan: "", secret };
    await unwrap(api.PUT("/api/characters/{character_id}/sire", { params: { path: { character_id: character.id } }, body }));
    onDone();
  });
  const ready = kind !== "linked" || !!linked;

  return (
    <Card title={`${character.name}'s sire`} className="mb-6">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="sr-only">Who the sire is</legend>
          {(
            [
              ["linked", "A vampire in the troupe"],
              ["named", "Someone known by name"],
              ["none", "Not known"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input type="radio" name="sire-kind" checked={kind === key} onChange={() => setKind(key)} />
              {label}
            </label>
          ))}
        </fieldset>
        {kind === "linked" &&
          (choices.isPending ? (
            <Loading compact />
          ) : choices.error ? (
            <ErrorText error={choices.error} />
          ) : (
            <Field label="Sire" hint={choices.data.length === 0 ? "No vampire in the troupe can be chosen. Name the sire instead." : "Those on the troupe's Who's Who."}>
              <Select value={linked} onChange={(e) => setLinked(e.target.value)}>
                <option value="">Choose…</option>
                {choices.data.map((c) => (
                  <option key={c.character_id} value={c.character_id}>
                    {c.name}
                    {c.clan ? ` (${c.clan})` : ""}
                  </option>
                ))}
              </Select>
            </Field>
          ))}
        {kind === "named" && (
          <>
            <Field label="Sire's name">
              <Input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} required />
            </Field>
            <Field label="Sire's clan" hint="Optional.">
              <Input value={clan} maxLength={100} onChange={(e) => setClan(e.target.value)} />
            </Field>
          </>
        )}
        {kind !== "none" && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
            <span>
              Keep it from the troupe’s players
              <span className="block text-xs text-mist">Its storytellers still see it. The sire lines players see leave it out.</span>
            </span>
          </label>
        )}
        <ErrorText error={save.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending || !ready}>
            Save sire
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
