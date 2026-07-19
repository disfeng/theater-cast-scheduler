from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    ACTOR = "actor"


class PerformanceStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class LeaveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    LOCKED = "locked"


class ActorNotificationTaskStatus(StrEnum):
    PENDING = "pending"
    REVEALED = "revealed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ActorNotificationType(StrEnum):
    NEW_ASSIGNMENT = "new_assignment"
    INFORMATION_UPDATED = "information_updated"
    SCHEDULE_CHANGED = "schedule_changed"
    SCHEDULE_CANCELLED = "schedule_cancelled"


class SmsDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DesignationType(StrEnum):
    UNIVERSAL = "universal"
    TOP_THREE = "top_three"
    PAIRED = "paired"


class RatingLevel(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    SUSPENDED = "suspended"


class BatchStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    SCHEDULED = "scheduled"


class ImportDraftStatus(StrEnum):
    DRAFT = "draft"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONFIRMED = "confirmed"


class DraftItemKind(StrEnum):
    DESIGNATION = "designation"
    WISH = "wish"
    UNRESOLVED = "unresolved"


class DraftValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class PlayerStatus(StrEnum):
    PROVISIONAL = "provisional"
    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"


class GrantBatchStatus(StrEnum):
    DRAFT = "draft"
    GRANTED = "granted"
    CANCELLED = "cancelled"


class EntitlementItemCategory(StrEnum):
    DESIGNATION = "designation"
    GENERAL = "general"


class EntitlementSourceType(StrEnum):
    MONTHLY_RANKING = "monthly_ranking"
    CAMPAIGN = "campaign"
    REISSUE = "reissue"
    MANUAL_ADJUSTMENT = "manual_adjustment"
    OTHER = "other"


class EntitlementItemStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class EntitlementEventType(StrEnum):
    GRANTED = "granted"
    RESERVED = "reserved"
    RELEASED = "released"
    CONSUMED = "consumed"
    MANUALLY_CONSUMED = "manually_consumed"
    EXPIRED = "expired"
    REVOKED = "revoked"
    EXTENDED = "extended"
    RESTORED = "restored"
    ADJUSTED = "adjusted"


class BoardRevisionStatus(StrEnum):
    REVIEW_REQUIRED = "review_required"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class BoardParserType(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"


class BoardItemKind(StrEnum):
    PLAYER = "player"
    DESIGNATION = "designation"
    WISH = "wish"
    UNRESOLVED = "unresolved"


class BoardChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    REMOVED = "removed"


class BoardValidationStatus(StrEnum):
    VALID = "valid"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
