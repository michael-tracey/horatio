"""All models, imported so that `Base.metadata` knows every table."""

from horatio.models.approvals import Approval, HomeTroupeChange, ReconciliationItem
from horatio.models.audit import AuditEvent
from horatio.models.base import Base
from horatio.models.characters import Character, CharacterTrait, SheetVersion, XpEntry
from horatio.models.downtimes import (
    AllowanceAdjustment,
    Answer,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    Question,
    RandomTable,
    Response,
    Submission,
)
from horatio.models.people import AuthIdentity, Session, User
from horatio.models.rules import (
    ActionKind,
    AllowanceRule,
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
    "DowntimeCycle",
    "RandomTable",
    "Response",
    "Question",
    "Submission",
    "Approval",
    "AuditEvent",
    "AuthIdentity",
    "Base",
    "Character",
    "CharacterTitle",
    "CharacterTrait",
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
