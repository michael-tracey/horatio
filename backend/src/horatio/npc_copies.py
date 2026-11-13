"""An NPC copied from a retired player character (issue #764): when a character turns
villain, or its player can no longer run it, its home troupe's running staff take a
copy of it to play as an NPC.

**What is copied.** Its sheet as it stands: every trait (clan, sect, disciplines,
merits and flaws, backgrounds, Humanity or Path), its primary paths, its picture, its
backstory, its pronouns, its Jyhad card text, its sire and a ghoul's domitor. It is
copied the way a troupe imports a character file as an NPC
(horatio.troupe_import.fill_npc), from the file the character's export writes
(horatio.character_backup.export), so the two never differ. The copy is named
"[NPC] <name>" so it doesn't collide with the original in lists and searches.

**What is not.** Its XP history (an NPC keeps none), equipment, Retainers' own
records, titles and status, boons, blood bonds and the Vinculum, Lesser Harpy access
and its Who's Who entry: all of these stay with the original, and staff give the NPC
what it needs by hand. The copy starts active and off the Who's Who.

**The original** is unchanged and stays in its player's vault. Any retired character
can be copied, however it left (Final Death too: a character believed dead may not
be), and an active one never. Its player isn't told: the original's log has the copy
for staff, kept out of the player's own view of it (horatio.api.character_log).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, pictures, troupe_import
from horatio import character_backup as backup
from horatio.models import Character, Troupe, User
from horatio.sheets import conflict

PREFIX = "[NPC] "

# The log entry on the original, which its player doesn't see.
COPIED_AS_NPC = "character.copied_as_npc"


def copy_name(character: Character) -> str:
    return PREFIX + character.name


def refusal(db: Session, character: Character, troupe: Troupe) -> str | None:
    """Why the character can't be copied as an NPC of `troupe`, or None."""
    if character.kind != "pc":
        return f"{character.name} is already an NPC."
    if character.status == "active":
        return f"{character.name} is still active: only a retired character can be made an NPC."
    name = troupe_import.same_name(copy_name(character))
    taken = db.scalars(
        select(Character.name).where(
            Character.kind == "npc", Character.owner_troupe_id == troupe.id
        )
    )
    if any(troupe_import.same_name(n) == name for n in taken):
        return f"The troupe already has an NPC named {copy_name(character)}."
    return None


def copy_as_npc(db: Session, staff: User, character: Character, troupe: Troupe) -> backup.Imported:
    """A copy of the retired `character` as a sheeted NPC of `troupe`, its home.
    Callers check `refusal` first, and commit."""
    reason = refusal(db, character, troupe)
    if reason is not None:
        raise conflict(reason)
    root = pictures.upload_dir()
    document = backup.export(db, character, root=root)
    document = document.model_copy(
        update={"character": document.character.model_copy(update={"name": copy_name(character)})}
    )
    # One entry of its own for the whole copy, not the import's and the backstory's.
    with audit.quiet(db):
        found = troupe_import.fill_npc(
            db, staff, troupe, document, root=root, files={}, write_pictures=True
        )
    npc = found.character
    # What the file carries only by name, copied as the original has it.
    npc.sire_id = character.sire_id
    npc.sire_name = character.sire_name
    npc.sire_clan = character.sire_clan
    npc.sire_secret = character.sire_secret
    npc.domitor_id = character.domitor_id
    npc.domitor_name = character.domitor_name
    npc.feeding_numbers = (
        dict(character.feeding_numbers) if character.feeding_numbers is not None else None
    )
    npc.visible_note = character.visible_note
    db.flush()
    player = db.get(User, character.player_id)
    handle = player.handle if player is not None else ""
    left_out = [i.label for i in found.items if i.status == "cannot"]
    audit.record(
        db,
        staff,
        "npc.copied_from_character",
        troupe_id=troupe.id,
        character_id=npc.id,
        original=character.name,
        original_id=character.id,
        from_handle=handle,
        left_out=len(left_out),
    )
    audit.record(
        db,
        staff,
        COPIED_AS_NPC,
        troupe_id=troupe.id,
        character_id=character.id,
        npc=npc.name,
        npc_id=npc.id,
    )
    return found
