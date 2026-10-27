import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/**
 * The character's less-used actions, behind a ⋯ button beside Play: Rename,
 * Pronouns, and Delete. `renameOn` is the first day a player who renamed lately can again;
 * the item says so instead of renaming.
 */
export function CharacterMenu({
  character,
  canRename,
  renameOn,
  onRename,
  onPronouns,
  canDelete,
}: {
  character: CharacterOut;
  canRename: boolean;
  renameOn: string | null;
  onRename: () => void;
  /** Set the character's pronouns, for those who may. */
  onPronouns?: () => void;
  canDelete: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const dates = useDates();
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  if (!canRename && !renameOn && !onPronouns && !canDelete) return null;
  const item = "block w-full px-3 py-2 text-left text-sm hover:bg-ash disabled:cursor-default disabled:text-mist disabled:hover:bg-transparent";

  return (
    <div ref={menu} className="relative">
      <Button variant="secondary" aria-label={`More for ${character.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        ⋯
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-1 w-60 overflow-hidden rounded-md border border-ash bg-dusk py-1 shadow-xl">
          {renameOn ? (
            <button type="button" role="menuitem" disabled className={item}>
              Rename
              <span className="block text-xs">You can rename {character.name} again on {dates.longDay(renameOn)}.</span>
            </button>
          ) : (
            canRename && (
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={() => {
                  setOpen(false);
                  onRename();
                }}
              >
                Rename…
              </button>
            )
          )}
          {onPronouns && (
            <button
              type="button"
              role="menuitem"
              className={item}
              onClick={() => {
                setOpen(false);
                onPronouns();
              }}
            >
              Pronouns…
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              role="menuitem"
              className={`${item} text-blood-bright`}
              onClick={() => {
                setOpen(false);
                setDeleting(true);
              }}
            >
              Delete…
            </button>
          )}
        </div>
      )}
      <Dialog title={`Delete ${character.name}`} open={deleting} onClose={() => setDeleting(false)}>
        <DeleteCharacter character={character} onCancel={() => setDeleting(false)} />
      </Dialog>
    </div>
  );
}

/** Deleting for good: a PC once it has left every troupe, an NPC by its troupe's staff. */
function DeleteCharacter({ character, onCancel }: { character: CharacterOut; onCancel: () => void }) {
  const navigate = useNavigate();
  const npc = character.kind === "npc";
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/characters/{character_id}", { params: { path: { character_id: character.id } } }));
    navigate(npc ? `/troupes/${character.owner_troupe_id}/npcs` : "/characters");
  });
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        {npc
          ? `Deleting removes the NPC ${character.name} and all of its history for good.`
          : `Deleting removes ${character.name} and all of its history for good. It is only possible once the character has left every troupe.`}
      </p>
      <ErrorText error={remove.error} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
          Delete {character.name} for good
        </Button>
      </div>
    </div>
  );
}
