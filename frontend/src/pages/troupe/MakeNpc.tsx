import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** The name its copy as an NPC takes (horatio.npc_copies). */
export function npcCopyName(name: string): string {
  return `[NPC] ${name}`;
}

/**
 * Copy a retired player character as an NPC of its home troupe (#764), for when it
 * turns villain or its player can no longer run it: what is copied and what stays,
 * then the new NPC's page.
 */
export function MakeNpc({ characterId, name, onDone }: { characterId: string; name: string; onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const npc = npcCopyName(name);
  const make = useAction(async () => {
    const made = await unwrap(api.POST("/api/characters/{character_id}/npc-copy", { params: { path: { character_id: characterId } } }));
    toast({
      message: made.left_out.length ? `Made ${made.character.name}. Left out: ${made.left_out.join(", ")}.` : `Made ${made.character.name}.`,
    });
    onDone();
    navigate(`/characters/${made.character.id}`);
  });
  return (
    <div className="flex flex-col gap-3">
      <ul className="list-disc space-y-1 pl-5 text-sm">
        <li>
          The troupe gets a new NPC, {npc}: a copy of {name}'s sheet as it stands, with its clan, sect, sire, backstory and picture.
        </li>
        <li>{name} stays as it is, retired, in its player's characters. Changing one never changes the other.</li>
        <li>Its boons, blood bonds, titles, status, equipment and Who's Who listing stay with {name}: give the NPC what it needs by hand.</li>
        <li>Its player isn't told.</li>
      </ul>
      <ErrorText error={make.error} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button disabled={make.isPending} onClick={() => make.mutate(undefined)}>
          Make {npc}
        </Button>
      </div>
    </div>
  );
}
