"""A character's Jyhad card (horatio.jyhad_card): for whoever can see the character,
its text written by whoever can edit it (its player, or staff for an NPC)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from horatio import crypt_templates, jyhad_card
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import can_edit_character, visible_character

router = APIRouter(tags=["jyhad card"])

TEXT_LENGTH = 300
FLAVOUR_LENGTH = 120


class CardDisciplineOut(BaseModel):
    name: str
    superior: bool
    # KRCG's symbol, if the custodian fetched them; else `abbreviation` shows.
    symbol: str | None
    # KRCG's three letters, as "aus".
    abbreviation: str
    # Whether `symbol` is KRCG's white-bordered one (#869), drawn as it is, on no plate.
    bordered: bool


class JyhadCardOut(BaseModel):
    character_id: uuid.UUID
    # Why the character has no card (not a vampire, no picture); None if it has one.
    missing: str | None
    name: str
    clan: str | None
    # KRCG's clan symbol, if fetched.
    clan_symbol: str | None
    # The sect, as the sheet has it ("Camarilla"), for the frame's colours.
    sect: str | None
    # "Camarilla Prince of Asheville: 2 votes", or the sect alone; None for neither.
    sect_line: str | None
    capacity: int | None
    # KRCG's capacity drop, if fetched; else the card draws one.
    capacity_symbol: str | None
    disciplines: list[CardDisciplineOut]
    # The character's picture (add "/portrait.webp").
    picture: str | None
    text: str
    flavour: str
    # The clan's crypt card template (#850), if the custodian uploaded one; else the
    # card is drawn on Horatio's own frame.
    template: str | None
    # Whether the viewer may write the text.
    can_write: bool


class CardTextIn(BaseModel):
    text: str = Field(max_length=TEXT_LENGTH)
    flavour: str = Field(max_length=FLAVOUR_LENGTH)


@router.get("/characters/{character_id}/jyhad-card")
def read_card(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> JyhadCardOut:
    character = visible_character(db, user, character_id)
    card = jyhad_card.card(db, character)
    return JyhadCardOut(
        character_id=character.id,
        missing=card.missing,
        name=card.name,
        clan=card.clan,
        clan_symbol=card.clan_symbol,
        sect=card.sect,
        sect_line=card.sect_line,
        capacity=card.capacity,
        capacity_symbol=card.capacity_symbol,
        disciplines=[CardDisciplineOut(**vars(d)) for d in card.disciplines],
        picture=card.picture,
        text=card.text,
        flavour=card.flavour,
        template=card.template,
        can_write=can_edit_character(db, user, character),
    )


@router.get("/characters/{character_id}/jyhad-card/template.webp", response_class=FileResponse)
def card_template(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> FileResponse:
    """The crypt card template the character's card is drawn on: only for whoever
    can see the character, as the templates are the Dark Pack's, not Horatio's."""
    character = visible_character(db, user, character_id)
    card = jyhad_card.card(db, character)
    path = crypt_templates.template_file(card.template_key) if card.template_key else None
    if card.missing or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This card has no template.")
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.put("/characters/{character_id}/jyhad-card/text")
def write_card_text(
    character_id: uuid.UUID, body: CardTextIn, db: DbSession, user: CurrentUser
) -> JyhadCardOut:
    """The card's text and italic flavour line: its player's to write, or staff's
    for an NPC. Nothing is suggested; empty leaves the box empty."""
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its player writes the card's text.")
    character.card_text = " ".join(body.text.split())
    character.card_flavour = " ".join(body.flavour.split())
    db.commit()
    return read_card(character_id, db, user)
