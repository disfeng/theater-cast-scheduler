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
