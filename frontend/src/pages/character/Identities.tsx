import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, IdentityOut } from "../../api/types";
import { Button, ErrorText, Input } from "../../components/ui";
import { useAction } from "../../hooks";

export function useIdentities(characterId: string) {
  return useQuery({
    queryKey: ["identities", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/identities", { params: { path: { character_id: characterId } } })),
  });
}

/** What an identity's rating stands up to, and who has Accepted it (MET: VtM core pp. 99, 310). */
export function IdentityNote({ identity, className = "text-xs text-mist" }: { identity: IdentityOut; className?: string }) {
  return (
    <p className={className}>
      {identity.line}
      {identity.accepted_by && <span className="text-parchment"> Accepted by {identity.accepted_by}.</span>}
    </p>
  );
}

/**
 * One Alternate Identity on the sheet, under its row: what its rating means,
 * and the sect or group that has Accepted it, which the player and staff set.
 */
export function IdentityPanel({ character, detail }: { character: CharacterOut; detail: string }) {
  const data = useIdentities(character.id);
  const [accepted, setAccepted] = useState<string | null>(null);
  const save = useAction((by: string) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/identities", {
        params: { path: { character_id: character.id } },
        body: { identities: [{ name: detail, accepted_by: by }] },
      }),
    ),
  );
  const identity = data.data?.identities.find((i) => i.name === detail);
  if (!data.data || !identity) return null;
  const label = detail || "Alternate Identity";
  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs" aria-label={`About ${label}`}>
      <IdentityNote identity={identity} />
      {accepted === null ? (
        data.data.can_edit &&
        detail && (
          <button className="mt-0.5 text-mist underline hover:text-gold" onClick={() => setAccepted(identity.accepted_by)}>
            {identity.accepted_by ? "Change who Accepts it" : "Accepted by a sect or group?"}
          </button>
        )
      ) : (
        <form
          className="mt-1 flex flex-wrap items-center gap-1.5"
          onSubmit={async (e) => {
            e.preventDefault();
            await save.mutateAsync(accepted.trim());
            setAccepted(null);
          }}
        >
          <Input aria-label={`Who Accepts ${label}`} value={accepted} onChange={(e) => setAccepted(e.target.value)} placeholder="Such as the Sabbat; empty for none" className="min-h-7 w-56 py-0.5 text-xs" />
          <Button type="submit" className="min-h-7 px-2 py-0.5 text-xs" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" className="min-h-7 px-2 py-0.5 text-xs" onClick={() => setAccepted(null)}>
            Cancel
          </Button>
        </form>
      )}
      <ErrorText error={save.error} />
    </div>
  );
}
