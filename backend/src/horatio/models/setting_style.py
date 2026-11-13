import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class ChronicleMotif(Record):
    """One entry of a troupe's Setting Style Document (horatio.setting_style): a
    theme, a mood or a storyteller note, which players read. Deleted outright:
    nothing holds it."""

    __tablename__ = "chronicle_motifs"
    __table_args__ = (
        CheckConstraint("kind in ('theme', 'mood', 'note')", name="kind"),
        # One entry at each place in its list. Checked at commit, so a reorder can
        # swap two places in one go.
        UniqueConstraint(
            "troupe_id",
            "kind",
            "position",
            name="uq_chronicle_motifs_place",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # "theme", "mood" or "note".
    kind: Mapped[str]
    # A theme's or mood's name, as its chip reads ("Betrayal"); empty for a note.
    name: Mapped[str] = mapped_column(default="", server_default="")
    # Markdown: a theme's questions, a mood's feel, or the note itself.
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The book's sample it was started from (data/bns_met_vampire_setting.toml), if any.
    book_key: Mapped[str | None]
    # Its place in its list, from 1.
    position: Mapped[int]
