"""All models, imported so that `Base.metadata` knows every table."""

from horatio.models.base import Base
from horatio.models.characters import Character, CharacterTrait, SheetVersion, XpEntry
from horatio.models.people import AuthIdentity, Session, User
from horatio.models.rules import CostRule, RuleSet, TraitCategory, TraitDefinition
from horatio.models.troupes import Troupe, TroupeMembership, TroupeStaff

__all__ = [
    "AuthIdentity",
    "Base",
    "Character",
    "CharacterTrait",
    "CostRule",
    "RuleSet",
    "Session",
    "SheetVersion",
    "TraitCategory",
    "TraitDefinition",
    "Troupe",
    "TroupeMembership",
    "TroupeStaff",
    "User",
    "XpEntry",
]
