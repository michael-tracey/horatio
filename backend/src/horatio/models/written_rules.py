import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class WrittenRule(Record):
    """A troupe's house rule in words alone (horatio.written_rules): one its players
    read, with nothing built from it, such as how Crafts difficulties work there or
    its FAQ. Deleted outright: nothing holds it."""

    __tablename__ = "written_rules"

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # The heading it is read under ("Disciplines", "FAQ"); empty for none.
    section: Mapped[str] = mapped_column(default="", server_default="")
    title: Mapped[str]
    # Markdown, as a backstory is written.
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Its place in its section.
    position: Mapped[int]
    # The book trait it is about, if one: it shows on that trait's details too. A house
    # merit's definition goes with the merit, and the link with it.
    trait_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trait_definitions.id", ondelete="SET NULL"), index=True
    )
    # The book page it is about, as a trait's page reads ("238", "Vol. 2, p. 50"), or
    # a link to the V20 LARP SRD.
    page: Mapped[str | None]
