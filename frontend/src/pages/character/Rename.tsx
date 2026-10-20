import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * Renaming a character. Its player can rename it once every 3 months while it is in
 * a troupe (any time before); the custodian can rename any character at any time;
 * an NPC's staff can rename it whenever they like. While the player has to wait,
 * the page says until when instead of offering this (see CharacterPage).
 */
export function RenameCharacter({ character, asCustodian, onDone }: { character: CharacterOut; asCustodian: boolean; onDone: () => void }) {
  const [name, setName] = useState(character.name);
  const rename = useAction(async () => {
    await unwrap(api.PATCH("/api/characters/{character_id}", { params: { path: { character_id: character.id } }, body: { name } }));
    onDone();
  });
  const hint = asCustodian
    ? "As custodian you can rename any character at any time. Its player and the storytellers of their troupes are told."
    : character.kind === "npc"
      ? "The new name can't be one another character in the troupe already has."
      : `While ${character.name} is in a troupe, you can rename it once every 3 months, and its storytellers are told. The new name can't be one another character in its troupes already has.`;

  return (
    <Card title={`Rename ${character.name}`} className="mb-6">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          rename.mutate(undefined);
        }}
      >
        <Field label="New name" hint={hint}>
          <Input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <ErrorText error={rename.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={rename.isPending || !name.trim() || name.trim() === character.name}>
            Rename
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
