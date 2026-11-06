"""Player Nominations (horatio.nominations): the troupe's setting; writing them in a
downtime; staff's review and publishing on the cycle; and reading them, on the
troupe's page, in its footer and on a character's page."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import audit, downtimes, leaving, nominations, pictures, remembrances, social_age
from horatio.api.downtimes import my_participation, staff_cycle, staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CycleParticipant, DowntimeCycle, Nomination, Troupe
from horatio.permissions import TroupeAction, can_edit_character, visible_character

router = APIRouter(tags=["nominations"])


class PlayerNominationsIn(BaseModel):
    on: bool


class PlayerNominationsOut(BaseModel):
    on: bool


class AboutOut(BaseModel):
    # One or the other: a character in the troupe, or one of its staff.
    character_id: uuid.UUID | None
    user_id: uuid.UUID | None
    name: str


class NominationIn(BaseModel):
    text: str = Field(max_length=nominations.TEXT_MOST)
    about_character_id: uuid.UUID | None = None
    about_user_id: uuid.UUID | None = None


class MyNominationOut(BaseModel):
    id: uuid.UUID
    text: str
    about: AboutOut | None
    # Published: it can no longer be changed by its writer.
    published: bool


class MyNominationsOut(BaseModel):
    nominations: list[MyNominationOut]
    # Who a nomination can be linked to.
    choices: list[AboutOut]
    # Whether the downtime is submitted: staff read them only once it is.
    submitted: bool
    # The most a nomination may say.
    most: int


class ReviewedOut(BaseModel):
    id: uuid.UUID
    text: str
    about: AboutOut | None
    # Who wrote it: for running staff only.
    character_id: uuid.UUID
    character_name: str
    player_name: str
    player_handle: str
    written_at: datetime
    removed: bool
    removed_reason: str
    starred: bool
    edited: bool
    published: bool


class RememberedReviewOut(BaseModel):
    """A character the cycle asks memories of, with those written so far."""

    remembrance_id: uuid.UUID
    character_id: uuid.UUID
    name: str
    picture: str | None
    # Why it left: Final Death, Off-field or Inactive.
    reason: str | None
    memories: list[ReviewedOut]


class CycleNominationsOut(BaseModel):
    # The troupe's settings: which of the two this tab reviews.
    player_nominations: bool
    remembrances_on: bool
    # The cycle's Player Nominations, and their counts.
    nominations: list[ReviewedOut]
    written: int
    removed: int
    starred: int
    # The characters the cycle asks memories of (horatio.remembrances).
    remembrances: list[RememberedReviewOut] = []
    # When they were first published, if they have been.
    published_at: datetime | None
    # Those not yet published, nor removed: what Publish (or Publish more) would add.
    waiting: int
    # The cycle is past Due, so they can be published.
    past_due: bool


class RemoveIn(BaseModel):
    reason: str = ""


class StarIn(BaseModel):
    starred: bool


class EditIn(BaseModel):
    text: str = Field(max_length=nominations.TEXT_MOST)


class PublishedOut(BaseModel):
    count: int


class EntryOut(BaseModel):
    id: uuid.UUID
    text: str
    # Who it is about, as plain text, when its writer linked it.
    about: str | None
    starred: bool
    edited: bool
    # Its place in its month's order, shuffled once as it was published.
    order: float


class RememberedOut(BaseModel):
    """A character remembered in a month, with the memories of them."""

    character_id: uuid.UUID
    name: str
    picture: str | None
    clan: str | None
    # Why it left: Final Death, Off-field or Inactive.
    reason: str | None
    memories: list[EntryOut]


class MonthOut(BaseModel):
    cycle_id: uuid.UUID
    name: str
    published_at: datetime
    nominations: list[EntryOut]
    # Those remembered this month (horatio.remembrances), by name.
    remembrances: list[RememberedOut] = []


class StarredOut(BaseModel):
    id: uuid.UUID
    text: str
    # The month it is from: its cycle's name.
    month: str


class AboutYouOut(BaseModel):
    id: uuid.UUID
    text: str
    month: str
    troupe_name: str


# --- helpers ----------------------------------------------------------------------------------


def about_out(db: DbSession, n: Nomination) -> AboutOut | None:
    name = nominations.about_name(db, n)
    if name is None:
        return None
    return AboutOut(character_id=n.about_character_id, user_id=n.about_user_id, name=name)


def choices_out(choices: list[nominations.About]) -> list[AboutOut]:
    return [AboutOut(character_id=a.character_id, user_id=a.user_id, name=a.name) for a in choices]


def my_nominations_out(
    db: DbSession, cycle: DowntimeCycle, participant: CycleParticipant
) -> MyNominationsOut:
    troupe = db.get_one(Troupe, cycle.troupe_id)
    nominations.require_on(troupe)
    submission = downtimes.submission_for(db, participant)
    return MyNominationsOut(
        nominations=[
            MyNominationOut(
                id=n.id, text=n.text, about=about_out(db, n), published=n.published_at is not None
            )
            for n in nominations.mine(db, participant)
        ],
        choices=choices_out(nominations.about_choices(db, troupe)),
        submitted=submission is not None and submission.status == "submitted",
        most=nominations.TEXT_MOST,
    )


def reviewed_out(db: DbSession, w: nominations.Written) -> ReviewedOut:
    return ReviewedOut(
        id=w.nomination.id,
        text=w.nomination.text,
        about=about_out(db, w.nomination),
        character_id=w.character.id,
        character_name=w.character.name,
        player_name=w.player.display_name,
        player_handle=w.player.handle,
        written_at=w.nomination.created_at,
        removed=w.nomination.removed_at is not None,
        removed_reason=w.nomination.removed_reason,
        starred=w.nomination.starred_at is not None,
        edited=w.nomination.edited_at is not None,
        published=w.nomination.published_at is not None,
    )


def cycle_nominations_out(db: DbSession, cycle: DowntimeCycle) -> CycleNominationsOut:
    troupe = db.get_one(Troupe, cycle.troupe_id)
    every = nominations.review(db, cycle)
    found = [w for w in every if w.nomination.remembrance_id is None]
    memories: dict[uuid.UUID, list[ReviewedOut]] = {}
    for w in every:
        if w.nomination.remembrance_id is not None:
            memories.setdefault(w.nomination.remembrance_id, []).append(reviewed_out(db, w))
    asked = remembrances.in_cycle(db, cycle) if remembrances.on(troupe) else []
    return CycleNominationsOut(
        player_nominations=troupe.player_nominations,
        remembrances_on=troupe.remembrances,
        nominations=[reviewed_out(db, w) for w in found],
        written=len(found),
        removed=sum(w.nomination.removed_at is not None for w in found),
        starred=sum(w.nomination.starred_at is not None for w in found),
        remembrances=[
            RememberedReviewOut(
                remembrance_id=r.remembrance.id,
                character_id=r.character.id,
                name=r.character.name,
                picture=pictures.picture_url(r.character.id, r.character.picture_id),
                reason=r.reason,
                memories=memories.get(r.remembrance.id, []),
            )
            for r in asked
        ],
        published_at=cycle.nominations_published_at,
        waiting=sum(
            w.nomination.published_at is None and w.nomination.removed_at is None for w in every
        ),
        past_due=downtimes.past_due(cycle),
    )


def review_cycle(db: DbSession, user: CurrentUser, cycle_id: uuid.UUID) -> DowntimeCycle:
    """A cycle whose nominations the user reviews: running staff, while the troupe
    uses them."""
    cycle, troupe = staff_cycle(db, user, cycle_id)
    nominations.require_reviewed(troupe)
    return cycle


def reviewed(
    db: DbSession, user: CurrentUser, nomination_id: uuid.UUID
) -> tuple[DowntimeCycle, Nomination]:
    found = db.get(Nomination, nomination_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such nomination.")
    cycle = review_cycle(db, user, found.cycle_id)
    return cycle, nominations.in_cycle(db, cycle, found.id)


def reading_troupe(db: DbSession, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or not nominations.can_read(db, user, troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Player Nominations to read here.")
    return troupe


# --- the setting --------------------------------------------------------------------------------


@router.put("/troupes/{troupe_id}/player-nominations")
def set_player_nominations(
    troupe_id: uuid.UUID, body: PlayerNominationsIn, db: DbSession, user: CurrentUser
) -> PlayerNominationsOut:
    """Switch Player Nominations on or off. Off, nothing of them shows anywhere; what
    was written and published is kept for when it is on again."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if troupe.player_nominations != body.on:
        troupe.player_nominations = body.on
        audit.record(
            db,
            user,
            "house.player_nominations",
            troupe_id=troupe.id,
            setting="on" if body.on else "off",
        )
    db.commit()
    return PlayerNominationsOut(on=troupe.player_nominations)


# --- writing them -------------------------------------------------------------------------------


@router.get("/characters/{character_id}/downtime/nominations")
def my_nominations(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyNominationsOut:
    """The nominations the character has written in its open downtime, and who they
    can be about."""
    _, cycle, participant = my_participation(db, user, character_id)
    return my_nominations_out(db, cycle, participant)


@router.post("/characters/{character_id}/downtime/nominations", status_code=201)
def write_nomination(
    character_id: uuid.UUID, body: NominationIn, db: DbSession, user: CurrentUser
) -> MyNominationsOut:
    character, cycle, participant = my_participation(db, user, character_id)
    nominations.write(
        db,
        character,
        cycle,
        participant,
        body.text,
        body.about_character_id,
        body.about_user_id,
    )
    db.commit()
    return my_nominations_out(db, cycle, participant)


@router.put("/characters/{character_id}/downtime/nominations/{nomination_id}")
def change_nomination(
    character_id: uuid.UUID,
    nomination_id: uuid.UUID,
    body: NominationIn,
    db: DbSession,
    user: CurrentUser,
) -> MyNominationsOut:
    character, cycle, participant = my_participation(db, user, character_id)
    nominations.change(
        db,
        character,
        cycle,
        participant,
        db.get(Nomination, nomination_id),
        body.text,
        body.about_character_id,
        body.about_user_id,
    )
    db.commit()
    return my_nominations_out(db, cycle, participant)


@router.delete("/characters/{character_id}/downtime/nominations/{nomination_id}")
def delete_nomination(
    character_id: uuid.UUID, nomination_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> MyNominationsOut:
    character, cycle, participant = my_participation(db, user, character_id)
    nominations.delete(db, character, cycle, participant, db.get(Nomination, nomination_id))
    db.commit()
    return my_nominations_out(db, cycle, participant)


# --- reviewing and publishing them ----------------------------------------------------------------


@router.get("/cycles/{cycle_id}/nominations")
def cycle_nominations(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleNominationsOut:
    """Every nomination in the cycle's submitted downtimes, with who wrote it, for
    running staff to review."""
    return cycle_nominations_out(db, review_cycle(db, user, cycle_id))


@router.post("/nominations/{nomination_id}/remove")
def remove_nomination(
    nomination_id: uuid.UUID, body: RemoveIn, db: DbSession, user: CurrentUser
) -> CycleNominationsOut:
    cycle, found = reviewed(db, user, nomination_id)
    nominations.remove(db, user, cycle, found, body.reason)
    db.commit()
    return cycle_nominations_out(db, cycle)


@router.post("/nominations/{nomination_id}/restore")
def restore_nomination(
    nomination_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CycleNominationsOut:
    cycle, found = reviewed(db, user, nomination_id)
    nominations.restore(db, user, cycle, found)
    db.commit()
    return cycle_nominations_out(db, cycle)


@router.put("/nominations/{nomination_id}/star")
def star_nomination(
    nomination_id: uuid.UUID, body: StarIn, db: DbSession, user: CurrentUser
) -> CycleNominationsOut:
    """Star it for the footer of the troupe's pages, or unstar it."""
    cycle, found = reviewed(db, user, nomination_id)
    nominations.star(db, user, cycle, found, body.starred)
    db.commit()
    return cycle_nominations_out(db, cycle)


@router.put("/nominations/{nomination_id}/text")
def edit_nomination(
    nomination_id: uuid.UUID, body: EditIn, db: DbSession, user: CurrentUser
) -> CycleNominationsOut:
    """A light edit by staff, marked as theirs."""
    cycle, found = reviewed(db, user, nomination_id)
    nominations.edit(db, user, cycle, found, body.text)
    db.commit()
    return cycle_nominations_out(db, cycle)


@router.post("/cycles/{cycle_id}/nominations/publish")
def publish_nominations(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PublishedOut:
    """Publish the cycle's nominations, or those written since they were, once it is
    past Due."""
    cycle = review_cycle(db, user, cycle_id)
    count = nominations.publish(db, user, cycle)
    db.commit()
    return PublishedOut(count=count)


# --- reading them ---------------------------------------------------------------------------------


def entry_out(db: DbSession, n: Nomination) -> EntryOut:
    return EntryOut(
        id=n.id,
        text=n.text,
        about=nominations.about_name(db, n),
        starred=n.starred_at is not None,
        edited=n.edited_at is not None,
        order=n.shuffle_key or 0.0,
    )


@router.get("/troupes/{troupe_id}/nominations")
def published_nominations(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[MonthOut]:
    """Each month's published nominations, newest month first, shuffled and without
    names: for the troupe's players and staff."""
    troupe = reading_troupe(db, user, troupe_id)
    months = nominations.published(db, troupe)
    clans = social_age.standings(db, [c.id for m in months for c, _ in m.remembered])
    return [
        MonthOut(
            cycle_id=m.cycle.id,
            name=m.cycle.name,
            published_at=m.cycle.nominations_published_at,  # type: ignore[arg-type]  # published
            nominations=[entry_out(db, n) for n in m.nominations],
            remembrances=[
                RememberedOut(
                    character_id=c.id,
                    name=c.name,
                    picture=pictures.picture_url(c.id, c.picture_id),
                    clan=clans[c.id].clan,
                    reason=leaving.reason_name(c.left_reason),
                    memories=[entry_out(db, n) for n in memories],
                )
                for c, memories in m.remembered
            ],
        )
        for m in months
    ]


@router.get("/troupes/{troupe_id}/nominations/starred")
def starred_nominations(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[StarredOut]:
    """Every starred nomination of the troupe's, from every month: what its footer
    rotates through. Empty for anyone who doesn't read them."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or not nominations.on(troupe) or not nominations.can_read(db, user, troupe):
        return []
    return [
        StarredOut(id=n.id, text=n.text, month=cycle.name)
        for cycle, n in nominations.starred(db, troupe)
    ]


@router.get("/characters/{character_id}/nominations")
def nominations_about(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[AboutYouOut]:
    """The published nominations about the character, newest month first, without
    names: for its player."""
    character: Character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character) or character.kind != "pc":
        return []
    troupes: dict[uuid.UUID, str] = {}
    out: list[AboutYouOut] = []
    for cycle, n in nominations.about_character(db, character):
        if cycle.troupe_id not in troupes:
            troupes[cycle.troupe_id] = db.get_one(Troupe, cycle.troupe_id).name
        out.append(
            AboutYouOut(
                id=n.id, text=n.text, month=cycle.name, troupe_name=troupes[cycle.troupe_id]
            )
        )
    return out
