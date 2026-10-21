"""What a character's game badge shows (issue #70): the name badges a troupe's
staff print for game, 3 × 5 in, two to a Letter page.

Top to bottom: the picture and the clan's logo, the name, clan and social age
(horatio.social_age), the titles the character holds in the troupe, its status
traits (with room for the stickers most troupes mark status with), in reversed
text what others can see or sense about it, and the troupe's name (#84).

What others can see comes from the rules data: a trait with a `visible`
property shows on the badge in those words, `{detail}` filled in with the
trait's detail ("Eerie Presence: {detail}" → "Eerie Presence: cold breeze").
Following a path other than Humanity is one such trait. A staff-written note
on the character covers anything the rules data does not.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import dark_pack, pictures, social_age, titles
from horatio.models import Character, CharacterTrait, ClanLogo, TraitCategory, TraitDefinition


@dataclass(frozen=True)
class Badge:
    character_id: uuid.UUID
    name: str
    clan: str | None
    social_age: str
    titles: list[str]
    status: list[str]
    visible: list[str]
    picture: str | None
    logo: str | None
    # The logo in white, for a dark badge; only Dark Pack symbols have one.
    logo_white: str | None


def wording(visible: str, detail: str) -> str:
    """A trait's badge wording with its detail filled in, or left out if it has none."""
    if not detail:
        return visible.replace(": {detail}", "").replace(" ({detail})", "").replace("{detail}", "")
    return visible.replace("{detail}", detail)


# A logo's address and its white version's (add "/600.webp"); None for none.
Logo = tuple[str | None, str | None]
NO_LOGO: Logo = (None, None)


def logos(db: Session, splat: str) -> dict[str, Logo]:
    """Each clan's logo address, and its white version's if it has one: the
    custodian's upload, or else the clan's Dark Pack symbol (horatio.dark_pack).
    A bloodline without its own takes its clan's."""
    found: dict[str, Logo] = dict(dark_pack.clan_logos()) if splat == "vampire" else {}
    for clan, image_id in db.execute(
        select(ClanLogo.clan, ClanLogo.image_id).where(ClanLogo.splat == splat)
    ):
        found[clan] = (pictures.logo_url(image_id), None)
    return found


def logo_for(found: dict[str, Logo], clan: str | None) -> Logo:
    if clan is None:
        return NO_LOGO
    return found.get(clan) or found.get(clan.split(":")[0].strip()) or NO_LOGO


def badges(
    db: Session, troupe_id: uuid.UUID | None, characters: Sequence[Character]
) -> list[Badge]:
    """The characters' badges, in the order given, with their titles in `troupe_id`."""
    ids = [c.id for c in characters]
    standing = social_age.standings(db, ids)
    status: dict[uuid.UUID, list[str]] = defaultdict(list)
    visible: dict[uuid.UUID, list[str]] = defaultdict(list)
    rows = db.execute(
        select(CharacterTrait, TraitDefinition, TraitCategory.key)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(CharacterTrait.character_id.in_(ids))
        .order_by(TraitDefinition.name, CharacterTrait.detail)
    )
    for trait, definition, category in rows:
        if trait.rating == 0:
            continue
        who = trait.character_id
        if category == "status_traits":
            named = f"{definition.name}: {trait.detail}" if trait.detail else definition.name
            status[who].append(named)
        said = definition.properties.get("visible")
        if isinstance(said, str):
            visible[who].append(wording(said, trait.detail))
    found_logos = {splat: logos(db, splat) for splat in {c.splat for c in characters}}
    out: list[Badge] = []
    for c in characters:
        note = [line.strip() for line in c.visible_note.splitlines() if line.strip()]
        clan = standing[c.id].clan
        logo, logo_white = logo_for(found_logos[c.splat], clan)
        out.append(
            Badge(
                character_id=c.id,
                name=c.name,
                clan=clan,
                social_age=standing[c.id].age,
                titles=titles.held(db, troupe_id, c.id) if troupe_id else [],
                status=status[c.id],
                visible=visible[c.id] + note,
                picture=pictures.picture_url(c.id, c.picture_id),
                logo=logo,
                logo_white=logo_white,
            )
        )
    return out
