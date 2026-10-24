"""All models, imported so that `Base.metadata` knows every table."""

from horatio.models.approvals import (
    Approval,
    DisciplinePurchase,
    HomeTroupeChange,
    ReconciliationItem,
)
from horatio.models.audit import AuditEvent
from horatio.models.base import Base
from horatio.models.characters import (
    Character,
    CharacterTrait,
    SheetVersion,
    TraitException,
    XpEntry,
)
from horatio.models.downtimes import (
    AllowanceAdjustment,
    Answer,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    FeedingAdjustment,
    OwedAction,
    Question,
    RandomTable,
    Response,
    Submission,
    TroupeConnector,
)
from horatio.models.influence import InfluenceEntry
from horatio.models.influence_blocks import InfluenceBlock
from horatio.models.influence_effects import InfluenceEffect
from horatio.models.notifications import EmailNotice, Notification
from horatio.models.people import AuthIdentity, FormerHandle, PasswordReset, Session, User
from horatio.models.play import PlayCounter, PlayEvent, PlayGame
from horatio.models.rules import (
    ActionKind,
    AllowanceRule,
    CheckOverride,
    ClanLogo,
    CostRule,
    CreationRule,
    RuleSet,
    StartingTrait,
    TraitCategory,
    TraitDefinition,
)
from horatio.models.shared_backgrounds import SharedBackground, SharedBackgroundEntry
from horatio.models.troupes import (
    CharacterTitle,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    TroupeRequest,
    TroupeSpecialization,
    TroupeStaff,
    TroupeTitle,
    XpRangeEntry,
)

__all__ = [
    "ActionKind",
    "AllowanceAdjustment",
    "AllowanceRule",
    "Answer",
    "CycleParticipant",
    "Delivery",
    "DisciplinePurchase",
    "DowntimeCycle",
    "EmailNotice",
    "FeedingAdjustment",
    "InfluenceBlock",
    "InfluenceEntry",
    "InfluenceEffect",
    "RandomTable",
    "Response",
    "Notification",
    "OwedAction",
    "PasswordReset",
    "PlayCounter",
    "PlayEvent",
    "PlayGame",
    "Question",
    "Submission",
    "TroupeConnector",
    "Approval",
    "AuditEvent",
    "AuthIdentity",
    "Base",
    "Character",
    "CharacterTitle",
    "CharacterTrait",
    "CheckOverride",
    "ClanLogo",
    "CostRule",
    "CreationRule",
    "FormerHandle",
    "HomeTroupeChange",
    "ReconciliationItem",
    "RuleSet",
    "ScheduledGame",
    "Session",
    "SharedBackground",
    "SharedBackgroundEntry",
    "SheetVersion",
    "StartingTrait",
    "TraitCategory",
    "TraitDefinition",
    "TraitException",
    "Troupe",
    "TroupeMembership",
    "TroupeRequest",
    "TroupeSpecialization",
    "TroupeStaff",
    "TroupeTitle",
    "User",
    "XpEntry",
    "XpRangeEntry",
]
