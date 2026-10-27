import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { PronounsInput } from "../../components/PronounsInput";
import { Button, Card, ErrorText, Field } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * The character's pronouns, set by its player (an NPC's by its troupe's staff). They
 * show beside its name, and on its badge if the troupe prints them; empty shows nothing.
 */
export function CharacterPronouns({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const [pronouns, setPronouns] = useState(character.pronouns ?? "");
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/characters/{character_id}/pronouns", { params: { path: { character_id: character.id } }, body: { pronouns } }));
    onDone();
  });

  return (
    <Card title={`${character.name}'s pronouns`} className="mb-6">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <Field label="Pronouns" hint="Optional, such as she/her or any. Leave empty for none.">
          <PronounsInput value={pronouns} onChange={(e) => setPronouns(e.target.value)} />
        </Field>
        <ErrorText error={save.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending}>
            Save pronouns
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
