import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import audit, closing, handles, pictures, sect_status, titles, xp_range
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    RuleSet,
    TraitCategory,
    TraitDefinition,
    Troupe,
    TroupeStaff,
    User,
)
from horatio.permissions import (
    Role,
    TroupeAction,
    require_custodian,
    require_troupe_action,
    troupe_roles,
    whos_who_troupes,
)
from horatio.rules.splats import SPLATS, splat_order

router = APIRouter(prefix="/troupes", tags=["troupes"])

STAFF_ROLES = (Role.STORYTELLER, Role.ASSISTANT_STORYTELLER, Role.NARRATOR)
# How the log says what status a troupe's badges print.
BADGE_STATUS_TEXT = {"all": "all status", "negative": "negative status only", "none": "no status"}


class TroupeOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    lead_user_id: uuid.UUID
    archived: bool
    # Sects whose player characters may join; empty means any.
    allowed_sects: list[str]
    # Splats whose player characters may join and be built for it ("vampire",
    # "ghoul"); never empty.
    allowed_splats: list[str]
    # The usual XP for a game session and for completing a downtime.
    session_xp: int
    downtime_xp: int
    # The XP a character had when the chronicle began, and the troupe's XP floor
    # and ceiling now (horatio.xp_range): a new character built for it starts at the floor.
    starting_xp: int
    xp_floor: int
    xp_ceiling: int
    # House rule: the blood characters start a game with; None for full.
    starting_blood: int | None
    # House rule: how many days back influence lookups look, from their cycle's close.
    influence_lookback_days: int
    # House rule: what a diablerie does to a Lesser Generation or Thin Blooded flaw:
    # leave | remove | keep_xp (horatio.diablerie).
    diablerie_flaws: str
    # House option: Golconda Seekers hold the innate status Enlightened (Vol. 2, p. 267).
    golconda_enlightened: bool = False
    # Status on sheets (horatio.sect_status): "players" keep their own fleeting and
    # negative status, naming the patron, or only "staff" add and remove it.
    status_by: str
    # Titles on sheets (horatio.titles): "players" choose their characters' titles
    # from their sect's, or only "staff" give them.
    titles_by: str
    # What its game badges print (horatio.badges): the titles held here or not, and
    # the status carried into a game here: "all", "negative" only, or "none".
    badge_titles: bool
    badge_status: str
    # Its badges print each character's pronouns (never the player's).
    badge_pronouns: bool
    # Its Who's Who (horatio.whos_who) shows the negative status each character
    # carries into a game here.
    whos_who_negative: bool
    # Quests (horatio.quests): on or off, and the requests each character may make in
    # a downtime cycle.
    quests_enabled: bool
    quest_requests_per_cycle: int
    # The caller may see its Who's Who: its staff, and the players of its characters.
    whos_who: bool
    # Its portrait (add "/48.webp", "/128.webp" or "/512.webp"), or None.
    portrait: str | None
    # Its banner, across the top of its page (add "/1500.webp" or "/750.webp"), or None.
    banner: str | None
    # Whether its profile shows to anyone, even people not signed in.
    public: bool
    # The caller's own role here, if any.
    my_role: Role | None


class NewTroupe(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    # The lead storyteller's handle.
    lead_handle: str


class TroupeChanges(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    allowed_sects: list[str] | None = None
    allowed_splats: list[str] | None = None
    session_xp: int | None = Field(default=None, ge=0, le=100)
    downtime_xp: int | None = Field(default=None, ge=0, le=100)
    starting_xp: int | None = Field(default=None, ge=0, le=10000)
    status_by: Literal["players", "staff"] | None = None
    titles_by: Literal["players", "staff"] | None = None
    badge_titles: bool | None = None
    badge_status: Literal["all", "negative", "none"] | None = None
    badge_pronouns: bool | None = None
    whos_who_negative: bool | None = None


class NewLead(BaseModel):
    handle: str


class StaffMember(BaseModel):
    user_id: uuid.UUID
    display_name: str
    handle: str
    role: Role


class StaffAssignment(BaseModel):
    handle: str
    role: Role


class Reason(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ClosingCharacter(BaseModel):
    character_id: uuid.UUID
    name: str
    # "NPC" for an NPC.
    player_name: str


class ClosingOut(BaseModel):
    """What archiving the troupe settles, or settled (horatio.closing)."""

    # Player characters it is home to, which are left with no home troupe.
    home: list[ClosingCharacter]
    # Player characters visiting it, whose visits end.
    visiting: list[ClosingCharacter]
    # Its NPCs, which stay with it.
    npcs: list[ClosingCharacter]
    # Its open downtime cycle, ended without being answered.
    cycle: str | None
    # Its own characters with a Play View game under way, which ends.
    games: list[ClosingCharacter]


class ArchivedCharacter(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str  # pc | npc
    player_id: uuid.UUID | None
    # "NPC" for an NPC.
    player_name: str
    # Its home troupe (or, for an NPC, its own troupe) was this one.
    home: bool
    # The troupe has let it go; otherwise it is still in it, waiting to be settled.
    left: bool


class ArchivedTroupeOut(BaseModel):
    id: uuid.UUID
    name: str
    archived_at: datetime
    # Who archived it, and why, from the audit log; None from before it said.
    archived_by_id: uuid.UUID | None
    archived_by_name: str | None
    reason: str | None
    lead_name: str
    # Its characters when it was archived.
    characters: list[ArchivedCharacter]
    # Something is still to settle: it was archived before archiving settled it.
    unsettled: bool


def given_reason(body: Reason) -> str:
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason.")
    return reason


def closing_out(db: DbSession, found: closing.Affected) -> ClosingOut:
    players = {
        u.id: u.display_name
        for u in db.scalars(
            select(User).where(User.id.in_([c.player_id for c in [*found.home, *found.visiting]]))
        )
    }

    def one(c: Character) -> ClosingCharacter:
        player = players[c.player_id] if c.kind == "pc" else "NPC"
        return ClosingCharacter(character_id=c.id, name=c.name, player_name=player)

    return ClosingOut(
        home=[one(c) for c in found.home],
        visiting=[one(c) for c in found.visiting],
        npcs=[one(c) for c in found.npcs],
        cycle=found.cycles[0].name if found.cycles else None,
        games=[one(c) for c in found.games],
    )


def troupe_out(db: DbSession, user: User, troupe: Troupe) -> TroupeOut:
    return troupes_out(db, user, [troupe])[0]


def troupes_out(db: DbSession, user: User, troupes: Sequence[Troupe]) -> list[TroupeOut]:
    """As `troupe_out` for each, asking the database a few times in all rather than
    a few times for each troupe: the list of troupes is asked for on many pages."""
    figures = xp_range.figures_of(db, troupes)
    roles = troupe_roles(db, user, troupes)
    whos_who = whos_who_troupes(db, user, troupes, roles)
    return [one_out(t, figures[t.id], roles[t.id], t.id in whos_who) for t in troupes]


def one_out(
    troupe: Troupe, figures: xp_range.Figures, role: Role | None, whos_who: bool
) -> TroupeOut:
    return TroupeOut(
        id=troupe.id,
        name=troupe.name,
        description=troupe.description,
        lead_user_id=troupe.lead_user_id,
        archived=troupe.archived_at is not None,
        allowed_sects=troupe.allowed_sects,
        allowed_splats=troupe.allowed_splats,
        session_xp=troupe.session_xp,
        downtime_xp=troupe.downtime_xp,
        starting_xp=troupe.starting_xp,
        xp_floor=figures.floor,
        xp_ceiling=figures.ceiling,
        starting_blood=troupe.starting_blood,
        influence_lookback_days=troupe.influence_lookback_days,
        diablerie_flaws=troupe.diablerie_flaws,
        golconda_enlightened=troupe.golconda_enlightened,
        status_by=troupe.status_by,
        titles_by=troupe.titles_by,
        badge_titles=troupe.badge_titles,
        badge_status=troupe.badge_status,
        badge_pronouns=troupe.badge_pronouns,
        whos_who_negative=troupe.whos_who_negative,
        quests_enabled=troupe.quests_enabled,
        quest_requests_per_cycle=troupe.quest_requests_per_cycle,
        whos_who=whos_who,
        portrait=pictures.troupe_portrait_url(troupe.id, troupe.portrait_id),
        banner=pictures.banner_url(troupe.id, troupe.banner_id),
        public=troupe.public,
        my_role=role,
    )


def staff_member(user: User, role: Role) -> StaffMember:
    return StaffMember(
        user_id=user.id, display_name=user.display_name, handle=user.handle, role=role
    )


def get_troupe(db: DbSession, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def existing_user(db: DbSession, handle: str) -> User:
    """Whoever has the handle, or had it lately (horatio.handles)."""
    user = handles.holder(db, handle) if handle.strip() else None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nobody has the handle {handle.strip()}.")
    return user


@router.get("")
def list_troupes(db: DbSession, user: CurrentUser) -> list[TroupeOut]:
    """Every troupe still running. Players need to see them to ask to join."""
    troupes = db.scalars(select(Troupe).where(Troupe.archived_at.is_(None)).order_by(Troupe.name))
    return troupes_out(db, user, list(troupes))


@router.get("/archived")
def list_archived(db: DbSession, user: CurrentUser) -> list[ArchivedTroupeOut]:
    """The custodian's list of archived troupes, latest first, with what each had."""
    require_custodian(user)
    troupes = list(
        db.scalars(
            select(Troupe)
            .where(Troupe.archived_at.is_not(None))
            .order_by(Troupe.archived_at.desc())
        )
    )
    events = closing.archived_by(db, [t.id for t in troupes])
    found: list[ArchivedTroupeOut] = []
    for troupe in troupes:
        assert troupe.archived_at is not None
        event = events.get(troupe.id)
        actor = db.get(User, event.actor_id) if event and event.actor_id else None
        left = closing.affected(db, troupe)
        characters = []
        for character, home, gone in closing.at_archiving(db, troupe):
            player = db.get_one(User, character.player_id) if character.kind == "pc" else None
            characters.append(
                ArchivedCharacter(
                    character_id=character.id,
                    name=character.name,
                    kind=character.kind,
                    player_id=player.id if player else None,
                    player_name=player.display_name if player else "NPC",
                    home=home,
                    left=gone,
                )
            )
        found.append(
            ArchivedTroupeOut(
                id=troupe.id,
                name=troupe.name,
                archived_at=troupe.archived_at,
                archived_by_id=actor.id if actor else None,
                archived_by_name=actor.display_name if actor else None,
                reason=event.data.get("reason") if event else None,
                lead_name=db.get_one(User, troupe.lead_user_id).display_name,
                characters=characters,
                unsettled=bool(left.characters or left.cycles or left.games),
            )
        )
    return found


@router.post("", status_code=status.HTTP_201_CREATED)
def create_troupe(body: NewTroupe, db: DbSession, user: CurrentUser) -> TroupeOut:
    """The custodian sets up a troupe and names its lead storyteller."""
    require_custodian(user)
    lead = existing_user(db, body.lead_handle)
    troupe = Troupe(name=body.name, description=body.description, lead_user_id=lead.id)
    db.add(troupe)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/{troupe_id}")
def read_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeOut:
    troupe = get_troupe(db, troupe_id)
    if troupe.archived_at is not None and not user.is_custodian:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe_out(db, user, troupe)


@router.patch("/{troupe_id}")
def change_troupe(
    troupe_id: uuid.UUID, body: TroupeChanges, db: DbSession, user: CurrentUser
) -> TroupeOut:
    troupe = get_troupe(db, troupe_id)
    if body.name is not None:
        require_troupe_action(db, user, troupe, TroupeAction.RENAME)
        troupe.name = body.name
        audit.record(db, user, "troupe.renamed", troupe_id=troupe.id, name=body.name)
    if body.description is not None:
        require_troupe_action(db, user, troupe, TroupeAction.EDIT_DESCRIPTION)
        troupe.description = body.description
    if body.allowed_sects is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        known = set(
            db.scalars(
                select(TraitDefinition.name)
                .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
                .where(TraitCategory.key == "sect")
            )
        )
        unknown = sorted(set(body.allowed_sects) - known)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such sect: {', '.join(unknown)}."
            )
        troupe.allowed_sects = sorted(set(body.allowed_sects))
        audit.record(
            db,
            user,
            "troupe.sects_limited",
            troupe_id=troupe.id,
            sects=", ".join(troupe.allowed_sects) or "any",
        )
    if body.allowed_splats is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        known = set(db.scalars(select(RuleSet.splat)))
        unknown = sorted(set(body.allowed_splats) - known)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such splat: {', '.join(unknown)}."
            )
        if not body.allowed_splats:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A troupe takes at least one splat."
            )
        troupe.allowed_splats = sorted(set(body.allowed_splats), key=splat_order)
        audit.record(
            db,
            user,
            "troupe.splats_limited",
            troupe_id=troupe.id,
            splats=", ".join(SPLATS[s].label for s in troupe.allowed_splats),
        )
    if body.session_xp is not None or body.downtime_xp is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        if body.session_xp is not None:
            troupe.session_xp = body.session_xp
        if body.downtime_xp is not None:
            troupe.downtime_xp = body.downtime_xp
        audit.record(
            db,
            user,
            "troupe.xp_defaults",
            troupe_id=troupe.id,
            session_xp=troupe.session_xp,
            downtime_xp=troupe.downtime_xp,
        )
    if body.status_by is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        troupe.status_by = body.status_by
        audit.record(
            db,
            user,
            "troupe.status_by",
            troupe_id=troupe.id,
            setting=sect_status.SETTING_TEXT[body.status_by],
        )
    if body.titles_by is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        troupe.titles_by = body.titles_by
        audit.record(
            db,
            user,
            "troupe.titles_by",
            troupe_id=troupe.id,
            setting=titles.SETTING_TEXT[body.titles_by],
        )
    if body.badge_titles is not None or body.badge_status is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        if body.badge_titles is not None:
            troupe.badge_titles = body.badge_titles
        if body.badge_status is not None:
            troupe.badge_status = body.badge_status
        audit.record(
            db,
            user,
            "troupe.badges",
            troupe_id=troupe.id,
            titles="titles" if troupe.badge_titles else "no titles",
            status=BADGE_STATUS_TEXT[troupe.badge_status],
        )
    if body.badge_pronouns is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        if body.badge_pronouns != troupe.badge_pronouns:
            troupe.badge_pronouns = body.badge_pronouns
            audit.record(
                db,
                user,
                "troupe.badge_pronouns",
                troupe_id=troupe.id,
                pronouns="character pronouns" if body.badge_pronouns else "no pronouns",
            )
    if body.whos_who_negative is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        if body.whos_who_negative != troupe.whos_who_negative:
            troupe.whos_who_negative = body.whos_who_negative
            audit.record(
                db,
                user,
                "troupe.whos_who",
                troupe_id=troupe.id,
                status="negative status" if body.whos_who_negative else "no sect status",
            )
    if body.starting_xp is not None:
        # The floor and ceiling both start from it, so both move with it.
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        troupe.starting_xp = body.starting_xp
        audit.record(
            db, user, "troupe.starting_xp", troupe_id=troupe.id, starting_xp=troupe.starting_xp
        )
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/{troupe_id}/closing")
def preview_closing(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ClosingOut:
    """What archiving the troupe would settle; for an archived one, what is left to."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.ARCHIVE)
    return closing_out(db, closing.affected(db, troupe))


@router.post("/{troupe_id}/archive")
def archive_troupe(
    troupe_id: uuid.UUID, body: Reason, db: DbSession, user: CurrentUser
) -> ClosingOut:
    """Deleting a troupe archives it: closed to use, history kept. What it held is
    settled first (horatio.closing), and everyone affected is told."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.ARCHIVE)
    reason = given_reason(body)
    found = closing.archive(db, user, troupe, reason)
    out = closing_out(db, found)
    db.commit()
    return out


@router.post("/{troupe_id}/settle")
def settle_archived(
    troupe_id: uuid.UUID, body: Reason, db: DbSession, user: CurrentUser
) -> ClosingOut:
    """The custodian settles a troupe archived before archiving settled anything."""
    require_custodian(user)
    troupe = get_troupe(db, troupe_id)
    reason = given_reason(body)
    found = closing.settle_archived(db, user, troupe, reason)
    out = closing_out(db, found)
    db.commit()
    return out


@router.post("/{troupe_id}/reopen")
def reopen_troupe(
    troupe_id: uuid.UUID, body: Reason, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """The custodian reopens an archived troupe. Its characters do not come back."""
    require_custodian(user)
    troupe = get_troupe(db, troupe_id)
    reason = given_reason(body)
    closing.reopen(db, user, troupe, reason)
    db.commit()
    return troupe_out(db, user, troupe)


@router.put("/{troupe_id}/lead")
def appoint_lead(
    troupe_id: uuid.UUID, body: NewLead, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """The custodian appoints a troupe's lead storyteller."""
    require_custodian(user)
    troupe = get_troupe(db, troupe_id)
    lead = existing_user(db, body.handle)
    # The lead is never also listed as ordinary staff.
    staff_row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == lead.id
        )
    )
    if staff_row is not None:
        db.delete(staff_row)
    troupe.lead_user_id = lead.id
    audit.record(db, user, "troupe.lead_appointed", troupe_id=troupe.id, member=lead.display_name)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/{troupe_id}/staff")
def list_staff(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[StaffMember]:
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    lead = db.get_one(User, troupe.lead_user_id)
    staff = db.execute(
        select(User, TroupeStaff.role)
        .join(TroupeStaff, TroupeStaff.user_id == User.id)
        .where(TroupeStaff.troupe_id == troupe.id)
        .order_by(User.display_name)
    )
    return [staff_member(lead, Role.LEAD_STORYTELLER)] + [
        staff_member(u, Role(role)) for u, role in staff
    ]


@router.put("/{troupe_id}/staff")
def assign_staff(
    troupe_id: uuid.UUID, body: StaffAssignment, db: DbSession, user: CurrentUser
) -> StaffMember:
    """Add someone to the staff, or change their role."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_STAFF)
    if body.role not in STAFF_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The lead storyteller is appointed by the custodian.",
        )
    member = existing_user(db, body.handle)
    if member.id == troupe.lead_user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That person is the lead storyteller.")
    row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == member.id
        )
    )
    if row is None:
        row = TroupeStaff(troupe_id=troupe.id, user_id=member.id, role=body.role)
        db.add(row)
    else:
        row.role = body.role
    audit.record(
        db,
        user,
        "staff.assigned",
        troupe_id=troupe.id,
        member=member.display_name,
        role=body.role.value.replace("_", " "),
    )
    db.commit()
    return staff_member(member, body.role)


@router.delete("/{troupe_id}/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_staff(
    troupe_id: uuid.UUID, user_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_STAFF)
    row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == user_id
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person is not on the staff.")
    member = db.get_one(User, user_id)
    db.delete(row)
    audit.record(db, user, "staff.removed", troupe_id=troupe.id, member=member.display_name)
    db.commit()
