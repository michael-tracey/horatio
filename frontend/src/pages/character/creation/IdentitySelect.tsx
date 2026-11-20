import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CategoryOut, CharacterOut, SheetOut } from "../../../api/types";
import { ChoiceBox, type BoxChoice } from "../../../components/ChoiceBox";
import { ErrorText, Field } from "../../../components/ui";
import { useAction } from "../../../hooks";
import { rulesTroupe } from "../rules";
import { CUSTOM_ARCHETYPE } from "./logic";

/**
 * One of Concept's choices made from a list: clan, archetype, sect… A `ChoiceBox`,
 * each choice with what it is in a line (a clan's in-clan disciplines, an archetype's
 * summary) and its detail (a clan's weakness) under the list. What is picked shows
 * at once, saying "Saving…", while it is saved and the page read again; if the
 * server refuses it, the box goes back to what is saved and says why (#638).
 * "Other…" for the archetype is not saved here: `onOwn` says it was picked, or left.
 */
export function IdentitySelect({
  character,
  choice,
  sheet,
  catalogue,
  own = false,
  onOwn,
}: {
  character: CharacterOut;
  choice: CategoryOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  own?: boolean;
  onOwn?: (own: boolean) => void;
}) {
  const client = useQueryClient();
  const sheetKey = ["sheet", character.id];
  // The one picked, shown in place of what is saved until saving it is done, or refused.
  const [picked, setPicked] = useState<string | null>(null);
  const choose = useAction(
    async (name: string) => {
      const changed = await unwrap(
        api.PUT("/api/characters/{character_id}/traits", {
          params: { path: { character_id: character.id } },
          body: { category: choice.key, name, detail: "", rating: null, teacher: "" },
        }),
      );
      // The answer is the sheet as the change left it: shown as it is, not asked for again.
      await client.cancelQueries({ queryKey: sheetKey, exact: true });
      client.setQueryData(sheetKey, changed.sheet);
      return changed;
    },
    [],
    { answered: [sheetKey] },
  );
  const saved = sheet.traits.find((t) => t.category === choice.key)?.name ?? "";
  return (
    <div className="flex flex-col gap-1">
      <Field label={choice.name} hint={choose.isPending ? "Saving…" : undefined}>
        <ChoiceBox
          label={choice.name}
          placeholder="Choose…"
          value={own ? CUSTOM_ARCHETYPE : (picked ?? saved)}
          disabled={choose.isPending}
          choices={catalogue.traits.filter((t) => t.category === choice.key).map((t): BoxChoice => ({ value: t.name, label: t.name, trait: t }))}
          splat={character.splat}
          troupeId={rulesTroupe(character)}
          onChoose={(name) => {
            const mine = choice.key === "archetype" && name === CUSTOM_ARCHETYPE;
            if (choice.key === "archetype") onOwn?.(mine);
            if (mine) return;
            setPicked(name);
            choose.mutate(name, { onSettled: () => setPicked(null) });
          }}
        />
      </Field>
      <ErrorText error={choose.error} />
    </div>
  );
}
