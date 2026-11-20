"""A level for each audit event (issue #1062): debug, info or notice, so the
custodian can record debug events or not, and keep debug and info events only so
long. Events already kept take their action's level; notice ones are kept forever.

Revision ID: 0239
Revises: 0238
Create Date: 2026-11-19 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0239"
down_revision: str | None = "0238"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# horatio.audit.DEBUG and NOTICE as they stood.
DEBUG = ("troupe.join",)
NOTICE = (
    "status.added",
    "status.spent",
    "status.removed",
    "status.expired",
    "status.given_up",
    "status.lost",
    "status.cleared",
    "influence.changed",
    "influence.merged",
    "npc.copied_from_character",
    "character.retired",
    "troupe.settled",
    "troupe.archived",
    "npc.given",
    "npc.claimed",
    "character.renamed",
    "downtime.reminded",
    "mail.gave_up",
    "location.added",
    "location.changed",
    "location.forfeit",
    "location.negative_removed",
    "location.out_of_code",
    "location.over_limit",
    "location.quest_built",
    "location.quest_completed",
    "location.removed",
    "account.discord_linked",
    "account.discord_link_refused",
    "account.discord_unlinked",
    "account.email_change_started",
    "account.email_change_resent",
    "account.email_change_email_failed",
    "account.email_change_notice_failed",
    "account.email_change_cancelled",
    "account.email_changed",
    "account.handle_changed",
    "account.merged",
    "account.merge_email_failed",
    "account.password_changed",
    "account.password_reset",
    "account.reset_cancelled",
    "account.reset_email_failed",
    "account.reset_link",
    "account.reset_requested",
    "account.reset_sent",
    "account.suspended",
    "account.suspension_email_failed",
    "account.suspension_lifted",
    "account.view_as",
    "account.view_as_ended",
    "character.deleted",
    "npc.deleted",
    "character.moved",
    "troupe.reopened",
    "troupe.lead_appointed",
    "staff.assigned",
    "staff.removed",
    "troupe_request.made",
    "troupe_request.approved",
    "troupe_request.declined",
    "troupe_request.withdrawn",
    "backup.made",
    "backup.downloaded",
    "audit.exported",
    "appearance.loading_animation",
    "mail.sender_set",
    "mail.design_set",
    "mail.header_uploaded",
    "mail.header_removed",
    "clan_logo.uploaded",
    "clan_logo.removed",
    "crypt_templates.uploaded",
    "crypt_templates.removed",
)


def upgrade() -> None:
    op.add_column(
        "audit_events", sa.Column("level", sa.String(), server_default="info", nullable=False)
    )
    op.create_check_constraint("level", "audit_events", "level in ('debug', 'info', 'notice')")
    events = sa.table("audit_events", sa.column("action", sa.String()), sa.column("level"))
    op.execute(events.update().where(events.c.action.in_(NOTICE)).values(level="notice"))
    op.execute(events.update().where(events.c.action.in_(DEBUG)).values(level="debug"))
    op.create_index("ix_audit_events_level_created_at", "audit_events", ["level", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_level_created_at", table_name="audit_events")
    op.drop_column("audit_events", "level")
