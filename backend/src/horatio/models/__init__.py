"""All models, imported so that `Base.metadata` knows every table."""

from horatio.models.approvals import (
    Approval,
    DisciplinePurchase,
    HomeTroupeChange,
    ReconciliationItem,
)
from horatio.models.audit import AuditEvent
from horatio.models.base import Base
from horatio.models.characters import Character, CharacterTrait, SheetVersion, XpEntry
from horatio.models.downtimes import (
    AllowanceAdjustment,
    Answer,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    OwedAction,
    Question,
    RandomTable,
    Response,
    Submission,
)
from horatio.models.notifications import Notification
from horatio.models.people import AuthIdentity, Session, User
from horatio.models.rules import (
    ActionKind,
    AllowanceRule,
    CheckOverride,
    CostRule,
    CreationRule,
    RuleSet,
    StartingTrait,
    TraitCategory,
    TraitDefinition,
)
from horatio.models.troupes import (
    CharacterTitle,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    TroupeTitle,
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
    "RandomTable",
    "Response",
    "Notification",
    "OwedAction",
    "Question",
    "Submission",
    "Approval",
    "AuditEvent",
    "AuthIdentity",
    "Base",
    "Character",
    "CharacterTitle",
    "CharacterTrait",
    "CheckOverride",
    "CostRule",
    "CreationRule",
    "HomeTroupeChange",
    "ReconciliationItem",
    "RuleSet",
    "Session",
    "SheetVersion",
    "StartingTrait",
    "TraitCategory",
    "TraitDefinition",
    "Troupe",
    "TroupeMembership",
    "TroupeStaff",
    "TroupeTitle",
    "User",
    "XpEntry",
]
