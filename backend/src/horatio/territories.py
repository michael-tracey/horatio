"""Feeding territories, an optional feeding rule (MET: VTM Vol. 2, pp. 304-307), as a
troupe plays it when it switches the rule on (Troupe.feeding_territories).

A territory is an area of the domain where only the vampires its Authority names may
feed, rated Small to Large by how many vessels it holds (p. 304). It starts
unassigned; the Authority assigns it by proclamation, to a clan, a pack, a character
or herself (p. 305). Staff keep the list as the Authority proclaims it, and the
domain knows it, so every member of the troupe can read it.

Horatio runs feeding through downtimes, so:

- With book feeding, a character may feed in a territory once a cycle, which stands in
  for one feeding action without spending one. A territory holds as many characters
  a cycle as it has vessels; staff see when more than that feed there.
- With the Rack (horatio.rack), a territory's vessels are Feeding Cards set aside for
  it, which only its holders take, or a poacher.
- Feeding in a territory the character does not hold is poaching. Its holders can
  spend downtime actions patrolling it; for each, staff test the poacher with a simple
  challenge, and a lost one means the patroller caught them (p. 305).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, FeedingTerritory, Troupe, User
from horatio.sheets import conflict, unprocessable

PAGES = "Vol. 2, pp. 304-307"


@dataclass(frozen=True)
class Size:
    key: str
    name: str
    # Feeding Cards, or vessels, it holds.
    vessels: int
    # How many vampires it usually serves (p. 304).
    usual: str


SIZES: dict[str, Size] = {
    s.key: s
    for s in (
        Size("small", "Small", 2, "1 to 2"),
        Size("moderate", "Moderate", 4, "2 to 3"),
        Size("notable", "Notable", 6, "4 to 5"),
        Size("significant", "Significant", 8, "5 to 7"),
        Size("large", "Large", 10, "6 to 8"),
    )
}


def on(troupe: Troupe | None) -> bool:
    """Feeding territories are played: switched on, with feeding tracked."""
    from horatio.feeding import tracked

    return troupe is not None and tracked(troupe) and troupe.feeding_territories


def listed(db: Session, troupe: Troupe, *, archived: bool = False) -> list[FeedingTerritory]:
    query = select(FeedingTerritory).where(FeedingTerritory.troupe_id == troupe.id)
    if not archived:
        query = query.where(FeedingTerritory.archived_at.is_(None))
    return list(db.scalars(query.order_by(FeedingTerritory.name)))


def holds(territory: FeedingTerritory, character_id: uuid.UUID) -> bool:
    return str(character_id) in territory.holder_ids


def territory_of(db: Session, troupe: Troupe, territory_id: uuid.UUID) -> FeedingTerritory:
    found = db.get(FeedingTerritory, territory_id)
    if found is None or found.troupe_id != troupe.id:
        raise unprocessable("No such feeding territory in this troupe.")
    return found


def holder_names(db: Session, territory: FeedingTerritory) -> list[str]:
    ids = [uuid.UUID(i) for i in territory.holder_ids]
    if not ids:
        return []
    return list(
        db.scalars(select(Character.name).where(Character.id.in_(ids)).order_by(Character.name))
    )


@dataclass
class Spec:
    name: str
    size: str
    area: str
    held_by: str
    holder_ids: list[uuid.UUID]


def check(db: Session, troupe: Troupe, spec: Spec, territory: FeedingTerritory | None) -> None:
    if not spec.name.strip():
        raise unprocessable("Give the territory a name.")
    if spec.size not in SIZES:
        raise unprocessable(f"A territory is one of {', '.join(SIZES)}.")
    clash = db.scalar(
        select(FeedingTerritory.id).where(
            FeedingTerritory.troupe_id == troupe.id,
            FeedingTerritory.name == spec.name.strip(),
            FeedingTerritory.archived_at.is_(None),
        )
    )
    if clash is not None and (territory is None or clash != territory.id):
        raise conflict(f"There is already a territory called {spec.name.strip()!r}.")
    if spec.holder_ids:
        home = set(
            db.scalars(
                select(Character.id).where(
                    Character.id.in_(spec.holder_ids), Character.home_troupe_id == troupe.id
                )
            )
        )
        if home != set(spec.holder_ids):
            raise unprocessable("A territory can only be assigned to characters at home here.")


def save(
    db: Session, staff: User, troupe: Troupe, spec: Spec, territory: FeedingTerritory | None
) -> FeedingTerritory:
    """Add a territory, or change one: its size, where it is, and who it is assigned to."""
    check(db, troupe, spec, territory)
    found = territory or FeedingTerritory(troupe_id=troupe.id)
    found.name = spec.name.strip()
    found.size = spec.size
    found.area = spec.area.strip()
    found.held_by = spec.held_by.strip()
    found.holder_ids = list(dict.fromkeys(str(i) for i in spec.holder_ids))
    if territory is None:
        db.add(found)
    db.flush()
    audit.record(
        db,
        staff,
        "house.territory_saved" if territory is None else "house.territory_changed",
        troupe_id=troupe.id,
        name=found.name,
        size=SIZES[found.size].name,
        holders=", ".join(holder_names(db, found)) or found.held_by or "no one yet",
    )
    return found


def archive(db: Session, staff: User, troupe: Troupe, territory: FeedingTerritory) -> None:
    """Revoke a territory, or record it lost: it leaves the list, and is kept."""
    if territory.archived_at is not None:
        return
    territory.archived_at = datetime.now(UTC)
    db.flush()
    audit.record(db, staff, "house.territory_archived", troupe_id=troupe.id, name=territory.name)
