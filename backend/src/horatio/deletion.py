"""Deleting a character for good.

Only a character in no troupe can be deleted, so its player must first leave
every troupe, and each of those troupes' logs records that it left. Deletion
then records one last entry in every troupe the character was ever in, and
removes the character and everything that is only about it: its sheet, XP,
approvals, and its downtime submissions and their responses. The troupe logs
keep their entries, with the character's name.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    AllowanceAdjustment,
    Answer,
    Approval,
    AuditEvent,
    Character,
    CharacterTitle,
    CharacterTrait,
    CycleParticipant,
    Delivery,
    DisciplinePurchase,
    HomeTroupeChange,
    ReconciliationItem,
    Response,
    Retainer,
    SheetVersion,
    Submission,
    TraitException,
    TroupeMembership,
    User,
    XpEntry,
)
from horatio.sheets import conflict, memberships


def delete_character(db: Session, player: User, character: Character) -> None:
    """For a PC, its player deletes it once it is in no troupe. An NPC is deleted by
    its troupe's staff whenever they like."""
    if character.kind == "pc" and memberships(db, character):
        raise conflict("Remove the character from every troupe before deleting it.")

    name = character.name
    for troupe_id in db.scalars(
        select(TroupeMembership.troupe_id)
        .where(TroupeMembership.character_id == character.id)
        .distinct()
    ):
        audit.record(
            db,
            player,
            "npc.deleted" if character.kind == "npc" else "character.deleted",
            troupe_id=troupe_id,
            character_id=character.id,
            character_name=name,
        )
    db.flush()

    cid = character.id
    participants = select(CycleParticipant.id).where(CycleParticipant.character_id == cid)
    submissions = select(Submission.id).where(Submission.participant_id.in_(participants))
    answers = select(Answer.id).where(Answer.submission_id.in_(submissions))
    approvals = select(Approval.id).where(Approval.character_id == cid)
    changes = select(HomeTroupeChange.id).where(HomeTroupeChange.approval_id.in_(approvals))

    db.execute(delete(Response).where(Response.answer_id.in_(answers)))
    db.execute(delete(Delivery).where(Delivery.submission_id.in_(submissions)))
    db.execute(delete(Answer).where(Answer.submission_id.in_(submissions)))
    db.execute(delete(Submission).where(Submission.participant_id.in_(participants)))
    db.execute(
        delete(AllowanceAdjustment).where(AllowanceAdjustment.participant_id.in_(participants))
    )
    db.execute(delete(CycleParticipant).where(CycleParticipant.character_id == cid))
    db.execute(delete(XpEntry).where(XpEntry.character_id == cid))
    db.execute(
        delete(ReconciliationItem).where(ReconciliationItem.home_troupe_change_id.in_(changes))
    )
    db.execute(delete(TraitException).where(TraitException.character_id == cid))
    db.execute(delete(HomeTroupeChange).where(HomeTroupeChange.approval_id.in_(approvals)))
    db.execute(delete(DisciplinePurchase).where(DisciplinePurchase.approval_id.in_(approvals)))
    db.execute(delete(Approval).where(Approval.character_id == cid))
    db.execute(
        update(TroupeMembership)
        .where(TroupeMembership.character_id == cid)
        .values(approved_version_id=None)
    )
    db.execute(delete(TroupeMembership).where(TroupeMembership.character_id == cid))
    db.execute(delete(SheetVersion).where(SheetVersion.character_id == cid))
    db.execute(delete(Retainer).where(Retainer.character_id == cid))
    db.execute(update(Retainer).where(Retainer.npc_id == cid).values(npc_id=None))
    db.execute(delete(CharacterTrait).where(CharacterTrait.character_id == cid))
    db.execute(delete(CharacterTitle).where(CharacterTitle.character_id == cid))
    db.execute(update(AuditEvent).where(AuditEvent.character_id == cid).values(character_id=None))
    db.delete(character)
    db.flush()
