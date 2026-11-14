import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { ActionMenu, MENU_ITEM, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { usePopover } from "../../components/InfoButton";
import { Button, ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { MoveCharacter } from "../custodian/MoveCharacter";
import { ClaimLink, GiveToPlayer } from "../troupe/GiveNpc";
import { MakeNpc } from "../troupe/MakeNpc";
import { ExportBackup } from "./Backup";
import { PostAsNpc } from "./InCharacter";
import { DiablerieForm, diablerieAction, useDiablerie } from "./Diablerie";
import { RetireCharacter } from "./Leaving";

/**
 * The character's less-used actions, behind a ⋯ button beside Play, in groups:
 * Rename, Pronouns, Sire and Move to another player (the custodian's, for a PC); Give to a
 * player and Claim link (an NPC's storytellers', for one they can give); diablerie
 * (staff record it, the player asks them to); Export (backup), for its player or an
 * NPC's staff, retired or not; Make an NPC of a retired PC, for its home troupe's
 * staff (#764); Post in IC chat as NPC, for an NPC's storytellers and assistants while it
 * isn't retired (#884); Retire and Delete. `renameOn` is the
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
  onSire,
  canRetire = false,
  canDelete,
  canMove = false,
  canGive = false,
  canExport = false,
  canMakeNpc = false,
  canPostInCharacter = false,
}: {
  character: CharacterOut;
  canRename: boolean;
  renameOn: string | null;
  onRename: () => void;
  /** Set the character's pronouns, for those who may. */
  onPronouns?: () => void;
  /** Give a vampire its sire (#707), for those who may. */
  onSire?: () => void;
  canRetire?: boolean;
  canDelete: boolean;
  canMove?: boolean;
  /** Give the NPC to a player, or make a claim link for it. */
  canGive?: boolean;
  /** Export it as a file, as a backup (#567). */
  canExport?: boolean;
  /** Copy a retired PC as an NPC of its home troupe (#764). */
  canMakeNpc?: boolean;
  /** Post in the troupe's In-Character channel on Discord as the NPC (#884). */
  canPostInCharacter?: boolean;
}) {
  const [retiring, setRetiring] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [moving, setMoving] = useState(false);
  const [giving, setGiving] = useState<"give" | "claim" | null>(null);
  const [diablerie, setDiablerie] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [makingNpc, setMakingNpc] = useState(false);
  const [postingIc, setPostingIc] = useState(false);
  const dates = useDates();
  const diablerieList = useDiablerie(character);
  const diablerieItem = diablerieAction(diablerieList.data);
  if (!canRename && !renameOn && !onPronouns && !onSire && !canRetire && !canDelete && !canMove && !canGive && !canExport && !canMakeNpc && !canPostInCharacter && !diablerieItem) return null;

  return (
    <div>
      <ActionMenu label={`More for ${character.name}`}>
        <MenuGroup label="Name">
          {renameOn ? (
            <MenuItem disabled>
              Rename
              <span className="block text-xs">You can rename {character.name} again on {dates.longDay(renameOn)}.</span>
            </MenuItem>
          ) : (
            canRename && <MenuItem onSelect={onRename}>Rename…</MenuItem>
          )}
          {onPronouns && <MenuItem onSelect={onPronouns}>Pronouns…</MenuItem>}
          {onSire && <MenuItem onSelect={onSire}>Sire…</MenuItem>}
          {canMove && <MenuItem onSelect={() => setMoving(true)}>Move to another player…</MenuItem>}
        </MenuGroup>
        <MenuGroup label="Give to a player">
          {canGive && <MenuItem onSelect={() => setGiving("give")}>Give to a player…</MenuItem>}
          {canGive && <MenuItem onSelect={() => setGiving("claim")}>Claim link…</MenuItem>}
        </MenuGroup>
        <MenuGroup label="Diablerie">{diablerieItem && <MenuItem onSelect={() => setDiablerie(true)}>{diablerieItem}</MenuItem>}</MenuGroup>
        <MenuGroup label="Backup">{canExport && <MenuItem onSelect={() => setExporting(true)}>Export (backup)…</MenuItem>}</MenuGroup>
        <MenuGroup label="NPC">
          {canMakeNpc && <MenuItem onSelect={() => setMakingNpc(true)}>Make an NPC…</MenuItem>}
          {canPostInCharacter && <MenuItem onSelect={() => setPostingIc(true)}>Post in IC chat as NPC…</MenuItem>}
        </MenuGroup>
        <MenuGroup label="Leaving">
          {canRetire && <MenuItem onSelect={() => setRetiring(true)}>Retire…</MenuItem>}
          {canDelete && <DeleteItem character={character} onDelete={() => setDeleting(true)} />}
        </MenuGroup>
      </ActionMenu>
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
      {canGive && (
        <>
          <Dialog title={`Give ${character.name} to a player`} open={giving === "give"} onClose={() => setGiving(null)}>
            {giving === "give" && <GiveToPlayer npcId={character.id} npcName={character.name} troupeId={character.home_troupe_id ?? ""} onDone={() => setGiving(null)} />}
          </Dialog>
          <Dialog title={`Claim link for ${character.name}`} open={giving === "claim"} onClose={() => setGiving(null)}>
            {giving === "claim" && <ClaimLink npcId={character.id} />}
          </Dialog>
        </>
      )}
      {canExport && (
        <Dialog title={`Export ${character.name}`} open={exporting} onClose={() => setExporting(false)}>
          {exporting && <ExportBackup character={character} onDone={() => setExporting(false)} />}
        </Dialog>
      )}
      {canMakeNpc && (
        <Dialog title={`Make an NPC of ${character.name}`} open={makingNpc} onClose={() => setMakingNpc(false)}>
          {makingNpc && <MakeNpc characterId={character.id} name={character.name} onDone={() => setMakingNpc(false)} />}
        </Dialog>
      )}
      {canPostInCharacter && (
        <Dialog title={`Post in IC chat as ${character.name}`} open={postingIc} onClose={() => setPostingIc(false)}>
          {postingIc && <PostAsNpc character={character} onDone={() => setPostingIc(false)} />}
        </Dialog>
      )}
      <Dialog title={`Retire ${character.name}`} open={retiring} onClose={() => setRetiring(false)}>
        <RetireCharacter character={character} onDone={() => setRetiring(false)} />
      </Dialog>
      <Dialog title={`Delete ${character.name}`} open={deleting} onClose={() => setDeleting(false)}>
        <DeleteCharacter character={character} onCancel={() => setDeleting(false)} />
      </Dialog>
    </div>
  );
}

/** Delete, in the open menu. The server deletes a PC only once it is in no troupe
 * (horatio.deletion), so for a PC it asks which troupes it is in, and is greyed
 * while asking and while it is in any. */
function DeleteItem({ character, onDelete }: { character: CharacterOut; onDelete: () => void }) {
  const pc = character.kind === "pc";
  const troupes = useQuery({
    queryKey: ["memberships", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/troupes", { params: { path: { character_id: character.id } } })),
    enabled: pc,
  });
  // The troupes a PC must leave before it can be deleted; undefined while asking.
  const inTroupes = pc ? troupes.data?.map((t) => t.troupe_name) : [];
  if (inTroupes === undefined) return <MenuItem disabled>Delete…</MenuItem>;
  if (inTroupes.length > 0) return <DeleteLater troupes={inTroupes} />;
  return (
    <MenuItem danger onSelect={onDelete}>
      Delete…
    </MenuItem>
  );
}

/** Why a PC in a troupe can't be deleted yet. */
export function deleteLaterReason(troupes: string[]): string {
  const names = troupes.length === 1 ? troupes[0] : `${troupes.slice(0, -1).join(", ")} and ${troupes.at(-1)}`;
  return `It can be deleted once it has left every troupe. It is in ${names}: leave from the Troupes tab, or retire it instead.`;
}

/** Delete, greyed: a tap shows why under it, as a hover title never shows on a phone. */
function DeleteLater({ troupes }: { troupes: string[] }) {
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
        className={`${MENU_ITEM} cursor-not-allowed text-mist hover:bg-transparent`}
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
    navigate(npc ? `/troupes/${character.owner_troupe_id}/characters?show=npcs` : "/characters");
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
