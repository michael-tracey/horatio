import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CategoryOut, CharacterOut, SheetOut } from "../../../api/types";
import { useClanName } from "../../../components/ClanNames";
import { ErrorText, Field, Select } from "../../../components/ui";
import { useAction } from "../../../hooks";
import { CUSTOM_ARCHETYPE } from "./logic";

/**
 * One of Concept's choices made from a list: clan, archetype, sect… What is picked
 * shows at once, saying "Saving…", while it is saved and the page read again; if the
 * server refuses it, the list goes back to what is saved and says why (#638).
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
  const named = useClanName();
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
        <Select
          value={own ? CUSTOM_ARCHETYPE : (picked ?? saved)}
          disabled={choose.isPending}
          onChange={(e) => {
            const name = e.target.value;
            if (!name) return;
            const mine = choice.key === "archetype" && name === CUSTOM_ARCHETYPE;
            if (choice.key === "archetype") onOwn?.(mine);
            if (mine) return;
            setPicked(name);
            choose.mutate(name, { onSettled: () => setPicked(null) });
          }}
        >
          <option value="">Choose…</option>
          {catalogue.traits
            .filter((t) => t.category === choice.key)
            .map((t) => (
              <option key={t.name} value={t.name}>
                {named(t.name)}
              </option>
            ))}
        </Select>
      </Field>
      <ErrorText error={choose.error} />
    </div>
  );
}
