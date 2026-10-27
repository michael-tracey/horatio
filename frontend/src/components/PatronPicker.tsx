import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { api, unwrap } from "../api/client";
import { CharacterPicker } from "./CharacterPicker";
import { Input } from "./ui";

export function usePatrons(characterId: string) {
  return useQuery({
    queryKey: ["status-patrons", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/status/patrons", { params: { path: { character_id: characterId } } })),
    staleTime: 60_000,
  });
}

/**
 * Who gave a status (MET: VTM p. 310): a search box over the home troupe's
 * characters, each with the title it holds there, and beside it a field for anyone
 * the list does not cover. One or both is needed. `troupe` names the home troupe.
 */
export function PatronPicker({
  characterId,
  troupe,
  patronId,
  patronText,
  onChange,
}: {
  characterId: string;
  troupe: string | null;
  patronId: string | null;
  patronText: string;
  onChange: (patronId: string | null, patronText: string) => void;
}) {
  const patrons = usePatrons(characterId);
  const textId = useId();

  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="mb-1 text-sm text-mist">
        Patron: who gave it. Pick {troupe ? `one of ${troupe}'s characters` : "a character"}, say who, or both.
      </legend>
      <CharacterPicker
        label="A character"
        listLabel="Patrons"
        choices={patrons.data ?? []}
        picked={patronId}
        onPick={(choice) => onChange(choice?.id ?? null, patronText)}
        none="No one matches. Say who in the other field."
      />
      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor={textId} className="text-mist">
          Or in your own words
        </label>
        <Input
          id={textId}
          value={patronText}
          maxLength={500}
          placeholder="Archon Halloran, at the Charlotte conclave"
          onChange={(e) => onChange(patronId, e.target.value)}
        />
      </div>
    </fieldset>
  );
}
