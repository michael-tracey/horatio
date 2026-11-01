import { useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { usePopover } from "../../components/InfoButton";
import { Button, ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { MoveCharacter } from "../custodian/MoveCharacter";
import { DiablerieForm, diablerieAction, useDiablerie } from "./Diablerie";
import { RetireCharacter } from "./Leaving";

/**
 * The character's less-used actions, behind a ⋯ button beside Play, in groups:
 * Rename, Pronouns and Move to another player (the custodian's, for a PC); diablerie
 * (staff record it, the player asks them to); Retire and Delete. `renameOn` is the
 * first day a player who renamed lately can again; the item says so instead of
 * renaming. `canDelete` is for those who may delete it at all: a PC's player, an
 * NPC's staff. A PC still in a troupe can't be deleted yet, and Delete says why.
 */
export function CharacterMenu({
  character,
  canRename,
  renameOn,
  onRename,
  onPronouns,
  canRetire = false,
  canDelete,
  canMove = false,
}: {
  character: CharacterOut;
  canRename: boolean;
  renameOn: string | null;
  onRename: () => void;
  /** Set the character's pronouns, for those who may. */
  onPronouns?: () => void;
  canRetire?: boolean;
  canDelete: boolean;
  canMove?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [moving, setMoving] = useState(false);
  const [diablerie, setDiablerie] = useState(false);
  const dates = useDates();
  const diablerieList = useDiablerie(character);
  const diablerieItem = diablerieAction(diablerieList.data);
  const menu = useRef<HTMLDivElement>(null);
  // It opens under the ⋯, lined up with its right edge; on a phone, where the ⋯ sits
  // left of centre, it slides back on screen.
  const list = useRef<HTMLDivElement>(null);
  const [shift, setShift] = useState(0);
  useLayoutEffect(() => {
    if (!open) return setShift(0);
    if (!list.current) return;
    const left = list.current.getBoundingClientRect().left;
    setShift(left < 8 ? 8 - left : 0);
  }, [open]);
  // The server deletes a PC only once it is in no troupe (horatio.deletion).
  const pc = character.kind === "pc";
  const troupes = useQuery({
    queryKey: ["memberships", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/troupes", { params: { path: { character_id: character.id } } })),
    enabled: open && canDelete && pc,
  });
  // The troupes a PC must leave before it can be deleted; undefined while asking.
  const inTroupes = pc ? troupes.data?.map((t) => t.troupe_name) : [];
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
  if (!canRename && !renameOn && !onPronouns && !canRetire && !canDelete && !canMove && !diablerieItem) return null;
  const item = "block w-full px-3 py-2 text-left text-sm hover:bg-ash disabled:cursor-default disabled:text-mist disabled:hover:bg-transparent";

  return (
    <div ref={menu} className="relative">
      <Button variant="secondary" aria-label={`More for ${character.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        ⋯
      </Button>
      {open && (
        <div
          ref={list}
          role="menu"
          style={shift ? { transform: `translateX(${shift}px)` } : undefined}
          className="absolute right-0 z-20 mt-1 w-64 overflow-hidden rounded-md border border-ash bg-dusk py-1 shadow-xl [&>[role=group]:not(:empty)~[role=group]:not(:empty)]:border-t [&>[role=group]:not(:empty)~[role=group]:not(:empty)]:border-ash"
        >
          <div role="group" aria-label="Name">
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
            {canMove && (
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={() => {
                  setOpen(false);
                  setMoving(true);
                }}
              >
                Move to another player…
              </button>
            )}
          </div>
          <div role="group" aria-label="Diablerie">
            {diablerieItem && (
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={() => {
                  setOpen(false);
                  setDiablerie(true);
                }}
              >
                {diablerieItem}
              </button>
            )}
          </div>
          <div role="group" aria-label="Leaving">
            {canRetire && (
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={() => {
                  setOpen(false);
                  setRetiring(true);
                }}
              >
                Retire…
              </button>
            )}
            {canDelete &&
              (inTroupes === undefined ? (
                <button type="button" role="menuitem" disabled className={item}>
                  Delete…
                </button>
              ) : inTroupes.length > 0 ? (
                <DeleteLater troupes={inTroupes} className={item} />
              ) : (
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
              ))}
          </div>
        </div>
      )}
      <Dialog title={`Move ${character.name} to another player`} open={moving} onClose={() => setMoving(false)}>
        <MoveCharacter characterId={character.id} characterName={character.name} playerId={character.player_id} onDone={() => setMoving(false)} />
      </Dialog>
      <Dialog
        title={diablerieList.data?.can_record ? `Record diablerie for ${character.name}` : "Ask staff about diablerie"}
        open={diablerie}
        onClose={() => setDiablerie(false)}
        phoneFull
      >
        {diablerieList.data && <DiablerieForm character={character} list={diablerieList.data} onClose={() => setDiablerie(false)} />}
      </Dialog>
      <Dialog title={`Retire ${character.name}`} open={retiring} onClose={() => setRetiring(false)}>
        <RetireCharacter character={character} onDone={() => setRetiring(false)} />
      </Dialog>
      <Dialog title={`Delete ${character.name}`} open={deleting} onClose={() => setDeleting(false)}>
        <DeleteCharacter character={character} onCancel={() => setDeleting(false)} />
      </Dialog>
    </div>
  );
}

/** Why a PC in a troupe can't be deleted yet. */
export function deleteLaterReason(troupes: string[]): string {
  const names = troupes.length === 1 ? troupes[0] : `${troupes.slice(0, -1).join(", ")} and ${troupes.at(-1)}`;
  return `It can be deleted once it has left every troupe. It is in ${names}: leave from the Troupes tab, or retire it instead.`;
}

/** Delete, greyed: a tap shows why under it, as a hover title never shows on a phone. */
function DeleteLater({ troupes, className }: { troupes: string[]; className: string }) {
  const { open, toggle, id, root, button } = usePopover();
  return (
    <span ref={root} className="block">
      <button
        ref={button}
        type="button"
        role="menuitem"
        aria-disabled="true"
        aria-describedby={id}
        aria-expanded={open}
        onClick={toggle}
        className={`${className} cursor-not-allowed text-mist hover:bg-transparent`}
      >
        Delete…
      </button>
      {/* Always there for the description; shown once tapped. */}
      <span id={id} className={`${open ? "block" : "hidden"} px-3 pb-2 text-xs text-mist`}>
        {deleteLaterReason(troupes)}
      </span>
    </span>
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
          : `Deleting removes ${character.name} and all of its history for good. The troupes it was in keep its name in their logs.`}
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
