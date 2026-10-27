"""What a character's game badge shows (issue #70): the name badges a troupe's
staff print for game, 3 × 5 in, two to a Letter page.

Top to bottom: the picture and the clan's logo, the name, clan and social age
(horatio.social_age), the titles the character holds in the troupe, the status it
carries into a game there (horatio.sect_status.carried, with the first source of
its abiding status), with room for the stickers most troupes mark status with, in
reversed text what others can see or sense about it, and the troupe's name (#84).

Each troupe chooses what prints (#255): its titles or not, and all the status,
the negative status only (which must be shown, MET: VTM p. 312), or none, leaving
the space for stickers. Negative status is marked out on the badge. It can print
the character's pronouns under its name (#265), off unless it chooses; a badge
never prints the player's.

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

from horatio import dark_pack, pictures, sect_status, social_age, titles
from horatio.models import Character, CharacterTrait, ClanLogo, TraitDefinition, Troupe
from horatio.rules.splats import SPLATS


@dataclass(frozen=True)
class Badge:
    character_id: uuid.UUID
    name: str
    # Its pronouns, if the troupe prints them and it has some.
    pronouns: str | None
    clan: str | None
    social_age: str
    titles: list[str]
    # The status it carries, but its negative status, which is apart to be marked
    # out; "Loyal ×2" for one held twice.
    status: list[str]
    negative: list[str]
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
    A bloodline without its own takes its clan's, and a ghoul its domitor's clan's."""
    splat = (SPLATS[splat].clans_from or splat) if splat in SPLATS else splat
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


def counted(names: Sequence[str]) -> list[str]:
    """Each name once, in order, with how many times if more than once."""
    times = dict.fromkeys(names, 0)
    for name in names:
        times[name] += 1
    return [f"{name} ×{n}" if n > 1 else name for name, n in times.items()]


def carried(
    db: Session, character: Character, troupe_id: uuid.UUID | None
) -> list[tuple[str, str]]:
    """The status the character carries into a game in `troupe_id`, as (name, type).
    In no troupe, it has no titles there: only its innate and held status."""
    if troupe_id is not None:
        return [(c.name, c.type) for c in sect_status.carried(db, character, troupe_id)]
    found = sect_status.standing(db, character)
    if found.sect_data is None:
        return []
    live = [
        h
        for h in found.held
        if h.status and found.own(h.status) and not (h.ending and h.ending.over)
    ]
    negative = [h for h in live if h.type == "Negative"]
    fleeting = [h for h in live if h.type == "Fleeting"][: found.fleeting_cap]
    innate = [(d.name, "Innate") for d in found.derived if d.kind == "merit"]
    return innate + [(h.name, h.type) for h in negative + fleeting]


def visible_to_others(db: Session, characters: Sequence[Character]) -> dict[uuid.UUID, list[str]]:
    """What others can see or sense about each character: its traits' `visible`
    wording, then the staff's note, a line each."""
    visible: dict[uuid.UUID, list[str]] = defaultdict(list)
    rows = db.execute(
        select(CharacterTrait, TraitDefinition)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .where(CharacterTrait.character_id.in_([c.id for c in characters]))
        .order_by(TraitDefinition.name, CharacterTrait.detail)
    )
    for trait, definition in rows:
        if trait.rating == 0:
            continue
        said = definition.properties.get("visible")
        if isinstance(said, str):
            visible[trait.character_id].append(wording(said, trait.detail))
    for c in characters:
        visible[c.id] += [line.strip() for line in c.visible_note.splitlines() if line.strip()]
    return visible


def badges(db: Session, troupe: Troupe | None, characters: Sequence[Character]) -> list[Badge]:
    """The characters' badges, in the order given, with their titles and status in
    `troupe`, as much of them as it prints."""
    troupe_id = troupe.id if troupe else None
    print_titles = troupe.badge_titles if troupe else True
    print_status = troupe.badge_status if troupe else "all"
    print_pronouns = troupe.badge_pronouns if troupe else False
    standing = social_age.standings(db, [c.id for c in characters])
    visible = visible_to_others(db, characters)
    found_logos = {splat: logos(db, splat) for splat in {c.splat for c in characters}}
    out: list[Badge] = []
    for c in characters:
        clan = standing[c.id].clan
        logo, logo_white = logo_for(found_logos[c.splat], clan)
        status = carried(db, c, troupe_id) if print_status != "none" else []
        out.append(
            Badge(
                character_id=c.id,
                name=c.name,
                pronouns=c.pronouns if print_pronouns else None,
                clan=clan,
                social_age=standing[c.id].age,
                titles=titles.held(db, troupe_id, c.id) if troupe_id and print_titles else [],
                status=counted([n for n, t in status if t != "Negative"])
                if print_status == "all"
                else [],
                negative=counted([n for n, t in status if t == "Negative"]),
                visible=visible[c.id],
                picture=pictures.picture_url(c.id, c.picture_id),
                logo=logo,
                logo_white=logo_white,
            )
        )
    return out
