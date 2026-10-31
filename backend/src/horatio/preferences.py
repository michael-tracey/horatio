"""Each person's settings (issue #100), saved on their account so they follow
them from one device to another.

`Preferences` lists every setting with its default. The account keeps only the
settings someone has changed (`users.preferences`), so changing a default here
changes it for everyone who kept it. The tickets that follow #100 each give a
setting its effect: #101 ratings, #102 time zone and dates, #104 paper and
badge size, #105 the Play View, #106 notifications by email, #107 text size.
"""

from typing import Any, Literal
from zoneinfo import available_timezones

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from horatio.models import User


class Preferences(BaseModel):
    # Settings no longer used are dropped quietly rather than refused.
    model_config = ConfigDict(extra="ignore")

    # How ratings show: as numbers, or as pips like the paper sheet (#101).
    ratings: Literal["numbers", "pips"] = "numbers"
    # An IANA zone such as "America/New_York"; None follows the browser (#102).
    time_zone: str | None = None
    # "20 Oct 2026", "10/20/2026" or "2026-10-20", on a 12- or 24-hour clock (#102).
    date_format: Literal["day_month", "month_day", "iso"] = "day_month"
    clock: Literal["12", "24"] = "12"
    # What printed sheets and badges are laid out for (#104).
    paper: Literal["letter", "a4"] = "letter"
    badge_size: Literal["3x5", "3x4", "cr80", "4x6"] = "3x5"
    # The Play View, as it opens (#105).
    quick_notes: bool = True
    keep_awake: bool = True
    play_tab: Literal["tracker", "sheet", "pools"] = "tracker"
    # Normal or larger text, everywhere but on paper (#107).
    text_size: Literal["normal", "large"] = "normal"
    # Which notifications also come by email, not only to the bell: each is off
    # until the person turns it on (#106, horatio.notification_emails.TOPICS).
    email_downtime: bool = False
    email_approvals: bool = False
    email_troupe_requests: bool = False
    email_renames: bool = False
    email_pictures: bool = False
    email_titles: bool = False
    # Each email as it happens, or everything gathered into one a day.
    email_digest: Literal["at_once", "daily"] = "at_once"
    # Troupes' Who's Who names the player by their handle, not their name (#264).
    whos_who_handle: bool = False

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, zone: str | None) -> str | None:
        if zone is not None and zone not in available_timezones():
            raise ValueError(f"{zone} is not a time zone Horatio knows.")
        return zone


def read(user: User) -> Preferences:
    """The person's settings, their changes over the defaults. A stored value
    that no longer passes (a setting's choices changed) falls back to its default."""
    try:
        return Preferences.model_validate(user.preferences or {})
    except ValidationError as error:
        bad = {str(e["loc"][0]) for e in error.errors() if e["loc"]}
        kept = {k: v for k, v in (user.preferences or {}).items() if k not in bad}
        return Preferences.model_validate(kept)


def change(user: User, changes: dict[str, Any]) -> Preferences:
    """Apply changes to some settings, refusing unknown settings and values. Only
    settings that differ from the default are kept on the account."""
    unknown = set(changes) - set(Preferences.model_fields)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such setting: {', '.join(sorted(unknown))}."
        )
    try:
        merged = Preferences.model_validate({**read(user).model_dump(), **changes})
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            error.errors()[0]["msg"].removeprefix("Value error, "),
        ) from error
    defaults = Preferences()
    user.preferences = {
        name: value
        for name, value in merged.model_dump().items()
        if value != getattr(defaults, name)
    }
    return merged
