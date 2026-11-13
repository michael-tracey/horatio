"""The Vinculum and the Vaulderie log (horatio.vinculum), for a Sabbat troupe that tracks
blood bonds: its running staff record Vaulderies, decide those players report, enter
background ties and see every rating; a player reports a Vaulderie their own character
took part in."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import bonds, vinculum
from horatio.api.bonds import PartyIn, PartyOut, bonds_troupe, party_out, players_character
from horatio.api.influence_log import CharacterChoice
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User, Vaulderie, VinculumTie
from horatio.permissions import visible_character

router = APIRouter(tags=["bonds"])


class VaulderieParticipantIn(PartyIn):
    # Drank but gave no blood (the Errata's p. 434).
    false_sabbat: bool = False


class VaulderieIn(BaseModel):
    night: date
    participants: list[VaulderieParticipantIn] = Field(max_length=vinculum.MOST_PARTICIPANTS)
    officiant: PartyIn | None = None
    # game | downtime | staff, checked in horatio.vinculum.
    source: str = "staff"
    note: str = Field(default="", max_length=2000)


class PlayerVaulderieIn(BaseModel):
    troupe_id: uuid.UUID
    night: date
    # The others who took part: the troupe's player characters by id, anyone else by name.
    others: list[VaulderieParticipantIn] = Field(max_length=vinculum.MOST_PARTICIPANTS)
    # The character itself drank but gave no blood.
    false_sabbat: bool = False
    officiant: PartyIn | None = None
    source: str = "game"
    note: str = Field(default="", max_length=2000)


class VaulderieDecideIn(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=2000)


class VinculumReasonIn(BaseModel):
    reason: str = Field(max_length=2000)


class VinculumTieIn(BaseModel):
    one: PartyIn
    other: PartyIn
    rating: int = Field(ge=1, le=5)
    night: date
    reason: str = Field(max_length=2000)


class VaulderieParticipantOut(BaseModel):
    who: PartyOut
    false_sabbat: bool


class VaulderieOut(BaseModel):
    id: uuid.UUID
    night: date
    participants: list[VaulderieParticipantOut]
    officiant: PartyOut | None
    # game | downtime | staff
    source: str
    note: str
    # recorded | pending | declined | withdrawn | removed
    status: str
    # Why it was declined or taken out.
    reason: str
    recorded_by: str | None
    at: datetime


class VinculumTieOut(BaseModel):
    id: uuid.UUID
    one: PartyOut
    other: PartyOut
    rating: int
    night: date
    reason: str


class VinculumPersonOut(BaseModel):
    # Stable within the response: a character's id, or "name:" and the name.
    key: str
    who: PartyOut


class VinculumRatingOut(BaseModel):
    # The one who feels it, toward the other.
    felt_by: str
    toward: str
    rating: int


class TroupeVinculumOut(BaseModel):
    """A Sabbat troupe's Vinculum, for its running staff: its Vaulderies (newest first,
    those waiting first of all), its background ties, and every rating now."""

    vaulderies: list[VaulderieOut]
    ties: list[VinculumTieOut]
    people: list[VinculumPersonOut]
    ratings: list[VinculumRatingOut]
    characters: list[CharacterChoice]


class VinculumOut(BaseModel):
    """A Vinculum the character feels, on its Bonds card: toward whom, and its rating."""

    troupe_id: uuid.UUID
    name: str
    rating: int
    effects: list[str]


class VaulderieTroupeOut(BaseModel):
    """A troupe its player can report the character's Vaulderies to, with the characters
    they can name in it by id."""

    id: uuid.UUID
    name: str
    characters: list[CharacterChoice]


def key_out(key: vinculum.Key) -> str:
    kind, value = key
    return value if kind == "c" else f"name:{value}"


def user_name(db: DbSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    found = db.get(User, user_id)
    return found.display_name if found is not None else None


def vaulderie_out(db: DbSession, vaulderie: Vaulderie) -> VaulderieOut:
    def who(character_id: uuid.UUID | None, name: str) -> PartyOut:
        character = db.get(Character, character_id) if character_id else None
        return party_out(character, name)

    officiant = (
        who(vaulderie.officiant_id, vaulderie.officiant_name)
        if vaulderie.officiant_id or vaulderie.officiant_name
        else None
    )
    return VaulderieOut(
        id=vaulderie.id,
        night=vaulderie.night,
        participants=[
            VaulderieParticipantOut(who=who(p.character_id, p.name), false_sabbat=p.false_sabbat)
            for p in vinculum.participants_of(db, vaulderie)
        ],
        officiant=officiant,
        source=vaulderie.source,
        note=vaulderie.note,
        status=vaulderie.status,
        reason=vaulderie.reason,
        recorded_by=user_name(db, vaulderie.recorded_by),
        at=vaulderie.created_at,
    )


def tie_out(db: DbSession, tie: VinculumTie) -> VinculumTieOut:
    one = vinculum.party_of(db, tie.one_id, tie.one_name)
    other = vinculum.party_of(db, tie.other_id, tie.other_name)
    return VinculumTieOut(
        id=tie.id,
        one=party_out(one.character, one.name),
        other=party_out(other.character, other.name),
        rating=tie.rating,
        night=tie.night,
        reason=tie.reason,
    )


def vinculum_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for its running staff, while it keeps the Vinculum."""
    troupe = bonds_troupe(db, user, troupe_id)
    if not vinculum.on(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't keep the Vinculum.")
    return troupe


def troupe_vaulderie(db: DbSession, troupe: Troupe, vaulderie_id: uuid.UUID) -> Vaulderie:
    found = db.get(Vaulderie, vaulderie_id)
    if found is None or found.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such Vaulderie.")
    return found


def staff_who(db: DbSession, troupe: Troupe, given: VaulderieParticipantIn) -> vinculum.Who:
    party = vinculum.participant(db, troupe, given.character_id, given.name)
    return vinculum.Who(party, given.false_sabbat)


def officiant_of(db: DbSession, troupe: Troupe, given: PartyIn | None) -> bonds.Party | None:
    if given is None:
        return None
    return vinculum.officiant_party(db, troupe, given.character_id, given.name)


@router.get("/troupes/{troupe_id}/vinculum")
def troupe_vinculum(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeVinculumOut:
    """The troupe's Vaulderies, background ties and every rating now, for its running
    staff."""
    troupe = vinculum_troupe(db, user, troupe_id)
    db.commit()
    every = list(
        db.scalars(
            select(Vaulderie)
            .where(Vaulderie.troupe_id == troupe.id, Vaulderie.status != "withdrawn")
            .order_by(Vaulderie.night.desc(), Vaulderie.created_at.desc(), Vaulderie.id.desc())
        )
    )
    every.sort(key=lambda v: v.status != "pending")
    known = vinculum.history(db, troupe)
    people = sorted(known.names.items(), key=lambda kv: kv[1].shown.casefold())
    choices = [
        c
        for c in db.scalars(
            select(Character).where(Character.status != "retired").order_by(Character.name)
        )
        if bonds.in_troupe(db, troupe, c) and bonds.is_vampire(c)
    ]
    return TroupeVinculumOut(
        vaulderies=[vaulderie_out(db, v) for v in every],
        ties=[tie_out(db, t) for t in vinculum.ties_of(db, troupe)],
        people=[
            VinculumPersonOut(key=key_out(k), who=party_out(p.character, p.name)) for k, p in people
        ],
        ratings=[
            VinculumRatingOut(felt_by=key_out(a), toward=key_out(b), rating=r)
            for (a, b), r in sorted(known.ratings().items())
        ],
        characters=[
            CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in choices
        ],
    )


@router.post("/troupes/{troupe_id}/vaulderies", status_code=status.HTTP_201_CREATED)
def record_vaulderie(
    troupe_id: uuid.UUID, body: VaulderieIn, db: DbSession, user: CurrentUser
) -> VaulderieOut:
    """Record a Vaulderie: it counts at once, and lowers each participant's blood bonds
    the troupe keeps a step (the Errata's p. 434)."""
    troupe = vinculum_troupe(db, user, troupe_id)
    people = [staff_who(db, troupe, p) for p in body.participants]
    done = vinculum.record(
        db,
        user,
        troupe,
        body.night,
        people,
        officiant_of(db, troupe, body.officiant),
        str(body.source),
        body.note,
    )
    db.commit()
    return vaulderie_out(db, done)


@router.post("/troupes/{troupe_id}/vaulderies/{vaulderie_id}/decide")
def decide_vaulderie(
    troupe_id: uuid.UUID,
    vaulderie_id: uuid.UUID,
    body: VaulderieDecideIn,
    db: DbSession,
    user: CurrentUser,
) -> VaulderieOut:
    """Approve a Vaulderie a player reported, or decline it with the reason."""
    troupe = vinculum_troupe(db, user, troupe_id)
    found = troupe_vaulderie(db, troupe, vaulderie_id)
    vinculum.decide(db, user, troupe, found, body.approve, body.reason)
    db.commit()
    return vaulderie_out(db, found)


@router.post("/troupes/{troupe_id}/vaulderies/{vaulderie_id}/remove")
def remove_vaulderie(
    troupe_id: uuid.UUID,
    vaulderie_id: uuid.UUID,
    body: VinculumReasonIn,
    db: DbSession,
    user: CurrentUser,
) -> VaulderieOut:
    """Take a recorded Vaulderie out, with the reason: it no longer counts toward
    ratings. The bonds it lowered stay lowered."""
    troupe = vinculum_troupe(db, user, troupe_id)
    found = troupe_vaulderie(db, troupe, vaulderie_id)
    vinculum.remove(db, user, troupe, found, body.reason)
    db.commit()
    return vaulderie_out(db, found)


@router.post("/troupes/{troupe_id}/vinculum/ties", status_code=status.HTTP_201_CREATED)
def add_tie(
    troupe_id: uuid.UUID, body: VinculumTieIn, db: DbSession, user: CurrentUser
) -> VinculumTieOut:
    """Enter a background tie: two who shared Vaulderies before Horatio, at a rating
    on a night (p. 435's example)."""
    troupe = vinculum_troupe(db, user, troupe_id)
    one = vinculum.participant(db, troupe, body.one.character_id, body.one.name)
    other = vinculum.participant(db, troupe, body.other.character_id, body.other.name)
    tie = vinculum.add_tie(db, user, troupe, one, other, body.rating, body.night, body.reason)
    db.commit()
    return tie_out(db, tie)


@router.post("/troupes/{troupe_id}/vinculum/ties/{tie_id}/remove")
def remove_tie(
    troupe_id: uuid.UUID,
    tie_id: uuid.UUID,
    body: VinculumReasonIn,
    db: DbSession,
    user: CurrentUser,
) -> TroupeVinculumOut:
    troupe = vinculum_troupe(db, user, troupe_id)
    tie = db.get(VinculumTie, tie_id)
    if tie is None or tie.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such tie.")
    vinculum.remove_tie(db, user, troupe, tie, body.reason)
    db.commit()
    return troupe_vinculum(troupe_id, db, user)


# --- a player's Vaulderies ----------------------------------------------------------------


def player_who(
    db: DbSession, troupe: Troupe, character: Character, given: VaulderieParticipantIn
) -> vinculum.Who:
    """Someone a player named: one of the troupe's player characters by id, or a name."""
    if given.character_id is not None:
        allowed = {c.id for c in bonds.player_choices(db, troupe, character)}
        if given.character_id not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Name that participant by name: only the troupe's player characters can be chosen.",
            )
    party = vinculum.participant(db, troupe, given.character_id, given.name)
    return vinculum.Who(party, given.false_sabbat)


@router.post("/characters/{character_id}/vaulderies", status_code=status.HTTP_201_CREATED)
def report_vaulderie(
    character_id: uuid.UUID, body: PlayerVaulderieIn, db: DbSession, user: CurrentUser
) -> VaulderieOut:
    """Its player reports a Vaulderie the character took part in: it waits for the
    troupe's running staff to approve it."""
    character = players_character(db, user, character_id)
    troupe = next(
        (t for t in vinculum.report_troupes(db, user, character) if t.id == body.troupe_id), None
    )
    if troupe is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Players don't report Vaulderies in that troupe."
        )
    me = vinculum.Who(bonds.Party(character, ""), body.false_sabbat)
    people = [me, *(player_who(db, troupe, character, p) for p in body.others)]
    officiant = None
    if body.officiant is not None and (body.officiant.character_id or body.officiant.name.strip()):
        officiant = player_who(
            db, troupe, character, VaulderieParticipantIn(**body.officiant.model_dump())
        ).party
    done = vinculum.report(
        db, user, troupe, character, body.night, people, officiant, body.source, body.note
    )
    db.commit()
    return vaulderie_out(db, done)


@router.post("/characters/{character_id}/vaulderies/{vaulderie_id}/withdraw")
def withdraw_vaulderie(
    character_id: uuid.UUID, vaulderie_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> VaulderieOut:
    """Take back a Vaulderie its player reported, while it waits."""
    character = players_character(db, user, character_id)
    found = db.get(Vaulderie, vaulderie_id)
    if found is None or found not in vinculum.reported_by(db, user, character):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such Vaulderie.")
    troupe = db.get_one(Troupe, found.troupe_id)
    vinculum.withdraw(db, user, troupe, found)
    db.commit()
    return vaulderie_out(db, found)


class CharacterVinculumOut(BaseModel):
    """For a character's Bonds card (#666)."""

    # The ratings it feels, as the reader may know of them: its player's own, and all
    # of them for the running staff of a troupe that keeps them.
    ratings: list[VinculumOut]
    # For its player: the troupes they can report its Vaulderies to.
    report_to: list[VaulderieTroupeOut]
    # For its player: the Vaulderies they reported for it that wait, or were declined
    # in the last month.
    reports: list[VaulderieOut]


@router.get("/characters/{character_id}/vinculum")
def character_vinculum(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterVinculumOut:
    """The Vinculum ratings the character feels, as the reader may know of them, and
    for its player, where they can report its Vaulderies and those they reported."""
    character = visible_character(db, user, character_id)
    felt = [
        VinculumOut(
            troupe_id=f.troupe.id,
            name=f.toward.shown,
            rating=f.rating,
            effects=vinculum.effects_of(f.rating, f.toward.shown),
        )
        for f in vinculum.felt_by(db, user, character)
    ]
    report_to = [
        VaulderieTroupeOut(
            id=t.id,
            name=t.name,
            characters=[
                CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True)
                for c in bonds.player_choices(db, t, character)
                if bonds.is_vampire(c)
            ],
        )
        for t in vinculum.report_troupes(db, user, character)
    ]
    reported = (
        [vaulderie_out(db, v) for v in vinculum.reported_by(db, user, character)]
        if bonds.plays(user, character)
        else []
    )
    return CharacterVinculumOut(ratings=felt, report_to=report_to, reports=reported)
