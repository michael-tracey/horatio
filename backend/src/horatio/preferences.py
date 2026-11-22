"""Each person's settings (issue #100), saved on their account so they follow
them from one device to another.

`Preferences` lists every setting with its default. The account keeps only the
settings someone has changed (`users.preferences`), so changing a default here
changes it for everyone who kept it. The tickets that follow #100 each give a
setting its effect: #101 ratings, #102 time zone and dates, #104 paper and
badge size, #105 the Play View, #106 notifications by email, #107 text size,
#635 the theme, #671 the Throws tab's pictures, #1196 the digest's day and hour
and quiet hours for phone notifications. Where each kind of notification
comes (#1053) is kept alongside them (horatio.notification_choices).
"""

import re
import uuid
from datetime import time
from typing import Any, Literal
from zoneinfo import available_timezones

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from horatio import notification_choices
from horatio.models import User

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS: tuple[Weekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
# A time of day as quiet hours keep it: "22:00", on a 24-hour clock.
CLOCK_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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
    play_tab: Literal["tracker", "sheet", "pools", "throws"] = "tracker"
    # The Throws tab's pictures (#671): None for Horatio's, or the id of a troupe the
    # person plays in whose own set they chose (horatio.api.throw_images). One they no
    # longer play in, or that removed its set, falls back to Horatio's.
    throw_images: str | None = None
    # Normal or larger text, everywhere but on paper (#107).
    text_size: Literal["normal", "large"] = "normal"
    # Dark, or Ultra goth: deep red on matte black (#635). Light isn't kept: it
    # only ever signs the person out (the frontend's Sunrise).
    theme: Literal["dark", "ultragoth"] = "dark"
    # Where each kind of notification comes, the bell or email, is kept here too, as
    # `email_downtime`, `bell_news` and so on, but isn't one of these: the topics of
    # horatio.notification_choices name them (#1053). `change` takes them, and `read`
    # leaves them out.

    # Each email as it happens, or everything gathered into one a day or a week, at
    # `digest_hour` in the person's time zone, on `digest_day` for a week's (#1196).
    # Word about their account's safety, and an announcement marked important, never
    # wait for it (horatio.notification_emails).
    email_digest: Literal["at_once", "daily", "weekly"] = "at_once"
    digest_hour: int = Field(default=8, ge=0, le=23)
    digest_day: Weekday = "monday"
    # Quiet hours for phone notifications (#1196): from `quiet_start` to `quiet_end`,
    # "HH:MM" in the person's time zone, pushes wait and come afterwards, gathered into
    # one. A few kinds come anyway (horatio.web_push.EXEMPT).
    quiet_hours: bool = False
    quiet_start: str = "22:00"
    quiet_end: str = "08:00"
    # Troupes' Who's Who names the player by their handle, not their name (#264).
    whos_who_handle: bool = False

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, zone: str | None) -> str | None:
        if zone is not None and zone not in available_timezones():
            raise ValueError(f"{zone} is not a time zone Horatio knows.")
        return zone

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def clock_time(cls, value: str) -> str:
        if not CLOCK_TIME.match(value):
            raise ValueError(f"{value} isn't a time of day, such as 22:00.")
        return value

    def quiet_times(self) -> tuple[time, time]:
        """When quiet hours start and end, as times of day."""
        return time.fromisoformat(self.quiet_start), time.fromisoformat(self.quiet_end)

    @field_validator("throw_images")
    @classmethod
    def troupe_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise ValueError("That isn't a troupe.") from error


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
    settings that differ from the default are kept on the account. Where a kind of
    notification comes is among them (horatio.notification_choices)."""
    unknown = set(changes) - set(Preferences.model_fields) - set(notification_choices.SETTINGS)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such setting: {', '.join(sorted(unknown))}."
        )
    try:
        choices = notification_choices.kept(changes)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    others = {k: v for k, v in changes.items() if k not in choices}
    try:
        merged = Preferences.model_validate({**read(user).model_dump(), **others})
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            error.errors()[0]["msg"].removeprefix("Value error, "),
        ) from error
    defaults = Preferences()
    stored = user.preferences or {}
    notices = {
        name: value
        for name, value in {
            **{k: v for k, v in stored.items() if k in notification_choices.SETTINGS},
            **choices,
        }.items()
        if value != notification_choices.SETTINGS[name]
    }
    user.preferences = {
        **{
            name: value
            for name, value in merged.model_dump().items()
            if value != getattr(defaults, name)
        },
        **notices,
        # And the characters' own Discord channels turned off (#1077), changed only
        # through Account › Notifications.
        **{k: v for k, v in stored.items() if k == notification_choices.OWN_CHANNELS_OFF},
    }
    return merged
