"""How Horatio looks, the same for everyone, which the custodian chooses: for now,
its loading animation (issue #568). Anyone may read it, signed in or not, as the
loading screen shows before anyone signs in.

The animation is kept by splat, with "default" for every splat without its own,
so a Werewolf or Changeling one can be added later without changing what is kept."""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import ServerSetting
from horatio.permissions import require_custodian
from horatio.rules.splats import SPLATS

router = APIRouter(prefix="/appearance", tags=["appearance"])

# The loading animations there are; the app draws each (frontend/src/loaders).
Motif = Literal["drip", "rising", "candle", "heartbeat"]
LOADING_ANIMATION = "loading_animation"
DEFAULT_LOADING: dict[str, Motif] = {"default": "drip"}
# Each as the audit log names it.
NAMES: dict[str, str] = {
    "drip": "blood drip",
    "rising": "rising blood",
    "candle": "candle",
    "heartbeat": "heartbeat",
}


class AppearanceOut(BaseModel):
    # The loading animation by splat: "default" for any splat not named.
    loading_animation: dict[str, Motif]


class LoadingAnimationIn(BaseModel):
    loading_animation: dict[str, Motif]


def loading_animation(db: DbSession) -> dict[str, Motif]:
    kept = db.get(ServerSetting, LOADING_ANIMATION)
    if kept is None:
        return dict(DEFAULT_LOADING)
    # Whatever was kept, with the default filled in.
    return {**DEFAULT_LOADING, **kept.value}


@router.get("")
def appearance(db: DbSession) -> AppearanceOut:
    return AppearanceOut(loading_animation=loading_animation(db))


@router.put("/loading-animation")
def set_loading_animation(
    body: LoadingAnimationIn, db: DbSession, user: CurrentUser
) -> AppearanceOut:
    """The custodian chooses the loading animation: one for every splat, and any
    splat that has its own."""
    require_custodian(user)
    chosen = body.loading_animation
    if "default" not in chosen:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a default animation.")
    unknown = sorted(k for k in chosen if k != "default" and k not in SPLATS)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"There is no splat {unknown[0]!r}."
        )
    before = loading_animation(db)
    kept = db.get(ServerSetting, LOADING_ANIMATION)
    if kept is None:
        db.add(ServerSetting(key=LOADING_ANIMATION, value=dict(chosen)))
    else:
        kept.value = dict(chosen)
    if before != chosen:
        record(
            db,
            user,
            "appearance.loading_animation",
            animation=NAMES[chosen["default"]],
            by_splat=dict(chosen),
        )
    db.commit()
    return AppearanceOut(loading_animation=loading_animation(db))
