"""The custodian merges two accounts of the same person (horatio.account_merges):
first a preview of what will move and what clashes, then the merge, with a reason."""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel

from horatio import account_merges
from horatio.api.character_moves import MoveTroupe, someone, troupe_out
from horatio.api.players import Someone
from horatio.api.troupes import existing_user
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import Role, require_custodian

router = APIRouter(prefix="/accounts/merge", tags=["custodian"])


class MergeCharacter(BaseModel):
    id: uuid.UUID
    name: str
    retired: bool
    # Its running troupes, home first.
    troupes: list[MoveTroupe]


class MergeStaff(BaseModel):
    troupe: MoveTroupe
    # The merged account's role there.
    role: Role
    # The staying account's role there before, if it had one (a clash), and after.
    had: Role | None
    keeps: Role
    # The change in words, as the logs give it.
    summary: str


class MergePreview(BaseModel):
    keep: Someone
    merge: Someone
    characters: list[MergeCharacter]
    staff: list[MergeStaff]
    # What it signs in with that moves: "Google", "Discord", "password".
    sign_in: list[str]
    # Its settings and profile that move, where the staying account has none.
    settings: list[str]
    # The handles that will find the staying account.
    handles: list[str]
    # The rest that moves, each as a phrase.
    others: list[str]
    # What else the merge does, each as a sentence: to a suspension, a change of
    # email waiting, a viewing as the account.
    also: list[str]
    # Why it can't be merged now, if it can't.
    refusals: list[str]


class MergeIn(BaseModel):
    # The handles of the account that stays and the one merged into it.
    keep: str
    merge: str
    reason: str


def preview_out(found: account_merges.Preview) -> MergePreview:
    return MergePreview(
        keep=someone(found.keep),
        merge=someone(found.other),
        characters=[
            MergeCharacter(
                id=c.id,
                name=c.name,
                retired=c.status == "retired",
                troupes=[troupe_out(t) for t in troupes],
            )
            for c, troupes in found.characters
        ],
        staff=[
            MergeStaff(
                troupe=troupe_out(s.troupe),
                role=Role(s.role),
                had=Role(s.had) if s.had else None,
                keeps=Role(s.keeps),
                summary=s.summary(found.keep),
            )
            for s in found.staff
        ],
        sign_in=found.sign_in,
        settings=found.settings,
        handles=found.handles,
        others=found.others,
        also=found.also,
        refusals=found.refusals,
    )


@router.get("")
def preview_merge(keep: str, merge: str, db: DbSession, user: CurrentUser) -> MergePreview:
    """What merging whoever has the handle `merge` into whoever has `keep` would do,
    for the custodian to confirm."""
    require_custodian(user)
    return preview_out(
        account_merges.preview(db, existing_user(db, keep), existing_user(db, merge), user)
    )


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def merge_accounts(body: MergeIn, db: DbSession, user: CurrentUser) -> None:
    """Merge one account into the other and close it. Only the custodian can, and only
    with a reason. It can't be undone."""
    require_custodian(user)
    account_merges.merge(
        db, user, existing_user(db, body.keep), existing_user(db, body.merge), body.reason
    )
    db.commit()
