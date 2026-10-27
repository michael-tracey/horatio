"""A troupe's Who's Who (horatio.whos_who), for its staff and the players of its
active characters, and what staff set for it: the court order of the troupe's own
titles, which untitled NPCs it lists, and whether it shows negative status (on the
troupe, horatio.api.troupes)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import audit, pictures, titles, whos_who
from horatio.api.downtimes import staff_troupe
from horatio.api.titles import TitlesOut, titles_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe
from horatio.permissions import TroupeAction, can_see_whos_who

router = APIRouter(tags=["whos-who"])


class WhosWhoEntry(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str  # pc | npc
    # Where its picture is (horatio.pictures), or None.
    picture: str | None
    # From the sheet as it stands, bloodline and all: "Brujah: True Brujah".
    clan: str | None
    # Neonate, Ancilla or Elder; a ghoul's splat ("Ghoul").
    social_age: str
    sect: str | None
    # The player's name, or their handle if they prefer; None for an NPC.
    player_id: uuid.UUID | None
    player_name: str | None
    # The titles it holds here, highest first.
    titles: list[str]
    # What others can see or sense about it, as its badge says.
    visible: list[str]
    # The status bans that apply to it: "Greater status ban: A known Caitiff.".
    bans: list[str]
    # The negative status it carries into a game here, if the troupe shows it.
    negative: list[str]
    # Visiting: its home troupe is elsewhere, named if it has one.
    visiting: bool
    visiting_from: str | None
    # Character and player pronouns (#265), who speaks for its clan at court if it
    # has no seat (#267), and why it left (#268): None until those are kept.
    pronouns: str | None
    player_pronouns: str | None
    represented_by: str | None
    left_reason: str | None


class ClanSection(BaseModel):
    # None for characters with no clan yet.
    clan: str | None
    character_ids: list[uuid.UUID]


class WhosWhoOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    # Everyone on it, by name; the views name them by id.
    entries: list[WhosWhoEntry]
    # Titled characters, highest title first.
    court: list[uuid.UUID]
    # One section per seated clan, by clan.
    clans: list[ClanSection]
    # Characters of clans with no seat at court.
    other: list[uuid.UUID]
    # Retired characters that were in the troupe and are listed, with why they left.
    departed: list[uuid.UUID]
    # The clans with a seat at court: those someone holds Primogen for here. None
    # seats every clan, as when no one holds Primogen.
    seated: list[str] | None
    # It shows the negative status each character carries into a game here.
    shows_negative: bool


class CourtOrder(BaseModel):
    # The troupe's own titles, each once, in their order at court.
    titles: list[str]


class Listed(BaseModel):
    listed: bool


def entry_out(entry: whos_who.Entry) -> WhosWhoEntry:
    c = entry.character
    return WhosWhoEntry(
        character_id=c.id,
        name=c.name,
        kind=c.kind,
        picture=pictures.picture_url(c.id, c.picture_id),
        clan=entry.clan,
        social_age=entry.social_age,
        sect=entry.sect,
        player_id=c.player_id if c.kind == "pc" else None,
        player_name=entry.player,
        titles=entry.titles,
        visible=entry.visible,
        bans=entry.bans,
        negative=entry.negative,
        visiting=entry.visiting,
        visiting_from=entry.visiting_from,
        pronouns=entry.pronouns,
        player_pronouns=entry.player_pronouns,
        represented_by=entry.represented_by,
        left_reason=entry.left_reason,
    )


@router.get("/troupes/{troupe_id}/whos-who")
def read_whos_who(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WhosWhoOut:
    """The troupe's active characters: its court, by clan, and Other. Only its staff
    and the players of active characters in it see it."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    if not can_see_whos_who(db, user, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The Who's Who is for the troupe's staff and the players of its characters.",
        )
    found = whos_who.whos_who(db, troupe)
    return WhosWhoOut(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        entries=[entry_out(e) for e in found.entries],
        court=found.court,
        clans=[ClanSection(clan=clan, character_ids=ids) for clan, ids in found.clans],
        other=found.other,
        departed=found.departed,
        seated=found.seated,
        shows_negative=troupe.whos_who_negative,
    )


@router.put("/troupes/{troupe_id}/court-order")
def set_court_order(
    troupe_id: uuid.UUID, body: CourtOrder, db: DbSession, user: CurrentUser
) -> TitlesOut:
    """Put the troupe's own titles in order at court, after the rule sets' titles."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.set_court_order(db, user, troupe, body.titles)
    db.commit()
    return titles_out(db, troupe)


@router.put("/troupes/{troupe_id}/npcs/{character_id}/whos-who")
def list_npc(
    troupe_id: uuid.UUID, character_id: uuid.UUID, body: Listed, db: DbSession, user: CurrentUser
) -> Listed:
    """List an NPC on the troupe's Who's Who though it holds no title, or stop."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    npc = db.get(Character, character_id)
    if npc is None or npc.kind != "npc" or npc.owner_troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such NPC in this troupe.")
    if npc.on_whos_who != body.listed:
        npc.on_whos_who = body.listed
        audit.record(
            db,
            user,
            "npc.whos_who",
            troupe_id=troupe.id,
            character_id=npc.id,
            listed="listed" if body.listed else "stopped listing",
        )
    db.commit()
    return Listed(listed=npc.on_whos_who)
