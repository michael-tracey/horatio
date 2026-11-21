"""All models, imported so that `Base.metadata` knows every table."""

from horatio.models.approvals import (
    Approval,
    DisciplinePurchase,
    HomeTroupeChange,
    ReconciliationItem,
)
from horatio.models.audit import AuditEvent
from horatio.models.auth_attempt import AuthAttempt
from horatio.models.backstories import (
    Backstory,
    BackstoryAnswer,
    BackstoryFeedback,
    BackstoryQuestion,
    BackstoryQuestionSet,
)
from horatio.models.base import Base
from horatio.models.bonds import BloodBond, BondEntry, BondReport
from horatio.models.boon_audits import BoonAudit
from horatio.models.boon_reviews import BoonFlag, BoonReportStaff
from horatio.models.boon_talons import BoonTalon
from horatio.models.boonbreakers import Boonbreaker
from horatio.models.boons import Boon, BoonEvent
from horatio.models.characters import (
    AppliedHouseTrait,
    Character,
    CharacterTrait,
    Diablerie,
    Embrace,
    SheetVersion,
    TraitException,
    XpEntry,
    XpPlan,
)
from horatio.models.discord_webhooks import DiscordWebhook
from horatio.models.downtimes import (
    AllowanceAdjustment,
    Answer,
    BackgroundChange,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    DowntimeKeyword,
    FeedingAdjustment,
    FeedingCard,
    FeedingTerritory,
    OwedAction,
    Project,
    ProjectCycle,
    Question,
    RandomTable,
    Response,
    Submission,
    TroupeConnector,
)
from horatio.models.email_changes import EmailChange
from horatio.models.equipment import EquipmentEvent, EquipmentItem, ResponseItem
from horatio.models.influence import InfluenceEntry
from horatio.models.influence_blocks import InfluenceBlock
from horatio.models.influence_effects import InfluenceEffect
from horatio.models.locations import Location, TroupeLocationQuality
from horatio.models.motif_tags import MotifTag
from horatio.models.nominations import Nomination, Remembrance
from horatio.models.notifications import EmailNotice, Notification, PushDevice, PushNotice
from horatio.models.npcs import InCharacterMessage, NpcClaim, StockNpc
from horatio.models.people import (
    AuthIdentity,
    FormerHandle,
    PasswordReset,
    Session,
    Suspension,
    User,
)
from horatio.models.play import (
    PlayCounter,
    PlayDerangement,
    PlayEffect,
    PlayEvent,
    PlayGame,
    PoolModifier,
)
from horatio.models.posts import NewsAgency, Post, PostDismissal, PostRead
from horatio.models.quests import (
    Quest,
    QuestLogEntry,
    QuestMember,
    QuestRequest,
    QuestRequirement,
    QuestScenario,
)
from horatio.models.recent_tabs import RecentTroupeTabs
from horatio.models.retainers import AlternateIdentity, Retainer, RetainerGrowth
from horatio.models.rules import (
    ActionKind,
    AllowanceRule,
    CheckOverride,
    ClanLogo,
    CostRule,
    CreationRule,
    EquipmentQuality,
    EquipmentTemplate,
    HouseCheck,
    HouseTrait,
    RuleSet,
    StartingTrait,
    TraitCategory,
    TraitDefinition,
    TraitOverride,
)
from horatio.models.scenes import Scene, SceneCharacter
from horatio.models.server_settings import ServerSetting
from horatio.models.setting_style import ChronicleMotif
from horatio.models.shared_backgrounds import SharedBackground, SharedBackgroundEntry
from horatio.models.status import HeldStatus, StatusBanMark, StatusSuppression
from horatio.models.story_bible import StoryBibleNote
from horatio.models.teachers import TeacherRule, Teaching
from horatio.models.troupes import (
    CalendarFeed,
    CharacterTitle,
    GameAttendance,
    GameRsvp,
    GameXpAward,
    ScheduledGame,
    TitleHolding,
    Troupe,
    TroupeMembership,
    TroupeRequest,
    TroupeSpecialization,
    TroupeStaff,
    TroupeTitle,
    XpRangeEntry,
)
from horatio.models.two_step import (
    AuthenticatorApp,
    Passkey,
    PasskeySignIn,
    RecoveryCode,
    SecondStepSignIn,
)
from horatio.models.viewing import Viewing
from horatio.models.vinculum import Vaulderie, VaulderieParticipant, VinculumTie
from horatio.models.written_rules import WrittenRule
from horatio.models.yorick_imports import YorickImport

__all__ = [
    "WrittenRule",
    "ChronicleMotif",
    "Backstory",
    "BloodBond",
    "BondEntry",
    "BondReport",
    "Boon",
    "BoonAudit",
    "BoonEvent",
    "BoonFlag",
    "BoonReportStaff",
    "BoonTalon",
    "Boonbreaker",
    "BackstoryAnswer",
    "BackstoryFeedback",
    "BackstoryQuestion",
    "BackstoryQuestionSet",
    "ActionKind",
    "AppliedHouseTrait",
    "HouseTrait",
    "HeldStatus",
    "AllowanceAdjustment",
    "AllowanceRule",
    "Answer",
    "BackgroundChange",
    "CycleParticipant",
    "Delivery",
    "Diablerie",
    "Embrace",
    "StatusBanMark",
    "StatusSuppression",
    "StoryBibleNote",
    "RecentTroupeTabs",
    "DisciplinePurchase",
    "DiscordWebhook",
    "DowntimeCycle",
    "DowntimeKeyword",
    "EmailNotice",
    "FeedingAdjustment",
    "FeedingCard",
    "FeedingTerritory",
    "EmailChange",
    "InfluenceBlock",
    "InfluenceEntry",
    "InfluenceEffect",
    "Location",
    "MotifTag",
    "TroupeLocationQuality",
    "RandomTable",
    "Response",
    "ResponseItem",
    "Nomination",
    "Remembrance",
    "Notification",
    "NewsAgency",
    "Post",
    "PostDismissal",
    "PostRead",
    "Passkey",
    "PasskeySignIn",
    "PushDevice",
    "PushNotice",
    "OwedAction",
    "Project",
    "ProjectCycle",
    "PasswordReset",
    "PlayCounter",
    "PoolModifier",
    "PlayDerangement",
    "PlayEffect",
    "PlayEvent",
    "PlayGame",
    "Question",
    "Quest",
    "QuestLogEntry",
    "QuestMember",
    "QuestRequest",
    "QuestRequirement",
    "QuestScenario",
    "Submission",
    "TroupeConnector",
    "Approval",
    "AuditEvent",
    "AuthAttempt",
    "AuthIdentity",
    "AuthenticatorApp",
    "Base",
    "Character",
    "CharacterTitle",
    "TitleHolding",
    "CharacterTrait",
    "CheckOverride",
    "HouseCheck",
    "TeacherRule",
    "Teaching",
    "ClanLogo",
    "ServerSetting",
    "CostRule",
    "CreationRule",
    "EquipmentEvent",
    "EquipmentItem",
    "EquipmentQuality",
    "EquipmentTemplate",
    "FormerHandle",
    "HomeTroupeChange",
    "ReconciliationItem",
    "RuleSet",
    "ScheduledGame",
    "GameRsvp",
    "GameAttendance",
    "GameXpAward",
    "CalendarFeed",
    "Scene",
    "SceneCharacter",
    "Session",
    "Suspension",
    "RecoveryCode",
    "Retainer",
    "RetainerGrowth",
    "AlternateIdentity",
    "SecondStepSignIn",
    "SharedBackground",
    "SharedBackgroundEntry",
    "SheetVersion",
    "StartingTrait",
    "InCharacterMessage",
    "NpcClaim",
    "StockNpc",
    "TraitCategory",
    "TraitDefinition",
    "TraitException",
    "TraitOverride",
    "Troupe",
    "TroupeMembership",
    "TroupeRequest",
    "TroupeSpecialization",
    "TroupeStaff",
    "TroupeTitle",
    "User",
    "Vaulderie",
    "VaulderieParticipant",
    "Viewing",
    "VinculumTie",
    "XpEntry",
    "XpPlan",
    "XpRangeEntry",
    "YorickImport",
]
