from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BoardItemKind


@dataclass(frozen=True)
class ParsedPerformancePlayer:
    player_name: str
    player_character_name: str
    paired_role_name: str
    relation_label: str | None
    theater_visit_ordinal: int | None
    character_visit_ordinal: int | None


class BoardItemPatch(BaseModel):
    item_kind: BoardItemKind | None = None
    player_name: str | None = Field(default=None, max_length=120)
    player_character_name: str | None = None
    paired_role_name: str | None = None
    relation_label: str | None = None
    theater_visit_ordinal: int | None = None
    character_visit_ordinal: int | None = None
    matched_player_id: int | None = None
    actor_id: int | None = None
    role_id: int | None = None
    note: str | None = None
    removal_lifecycle_confirmed: bool | None = None

    @field_validator("player_name")
    @classmethod
    def validate_player_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("player_identity_required")
        return value

    @field_validator("item_kind")
    @classmethod
    def validate_item_kind(cls, value: BoardItemKind | None) -> BoardItemKind | None:
        if value == BoardItemKind.UNRESOLVED:
            raise ValueError("manual_item_kind_required")
        return value


class BoardRevisionCreate(BaseModel):
    raw_text: str = Field(max_length=50_000)
    parse_with_ai: bool = True


class AiParserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    endpoint: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    model_name: str = Field(min_length=1, max_length=120)
    timeout_seconds: int = Field(ge=1, le=300)


class AiParserSettingsRead(BaseModel):
    enabled: bool
    endpoint: str
    api_key_masked: str | None
    model_name: str
    timeout_seconds: int
    prompt_version: str
    last_test_ok: bool | None
    last_test_message: str | None
    last_tested_at: object | None


class AiParserTestRead(BaseModel):
    ok: bool
    message: str


class BoardCandidateRead(BaseModel):
    field: str
    id: int
    label: str


class BoardDraftItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    revision_id: int
    item_kind: str
    change_type: str
    raw_line: str | None
    player_name: str | None
    player_character_name: str | None
    paired_role_name: str | None
    relation_label: str | None
    theater_visit_ordinal: int | None
    character_visit_ordinal: int | None
    actor_name_raw: str | None
    role_name_raw: str | None
    note: str | None
    matched_player_id: int | None
    actor_id: int | None
    role_id: int | None
    candidates: list[BoardCandidateRead] | None
    confidence: dict | None
    validation_status: str
    failure_reason: str | None
    confirmed_at: object | None
    removal_lifecycle_confirmed: bool
    performance_player_id: int | None = None
    wish_id: int | None = None


class BoardRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    board_id: int
    revision_number: int
    raw_text: str
    status: str
    parser_type: str
    created_at: object
    confirmed_at: object | None
    rollback_source_revision_id: int | None = None
    draft_items: list[BoardDraftItemRead] = []


class PerformanceBoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    performance_id: int
    current_revision_id: int | None
    revisions: list[BoardRevisionRead] = []


class DesignationActivateRequest(BaseModel):
    item_id: int | None = None
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)


class ProxyDesignationVerifyRequest(BaseModel):
    owner_player_id: int
    item_id: int
    note: str = Field(min_length=1, max_length=2000)
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)


class DesignationReplaceRequest(BaseModel):
    replaced_id: int
    expected_versions: dict[str, int]
    confirmed: bool = False
    idempotency_key: str = Field(min_length=1, max_length=120)


class DesignationCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason_required")
        return value.strip()


class DesignationCorrectionPatch(BaseModel):
    player_name: str | None = Field(default=None, min_length=1, max_length=120)
    actor_id: int | None = Field(default=None, gt=0)
    role_id: int | None = Field(default=None, gt=0)
    usage_type: str | None = None
    owner_player_id: int | None = Field(default=None, gt=0)
    entitlement_item_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: bool = False
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=120)


class WishCorrectionPatch(BaseModel):
    player_name: str | None = Field(default=None, min_length=1, max_length=120)
    actor_id: int | None = None
    role_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: bool = False
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def reject_blank_correction_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("correction_reason_required")
        return value.strip()

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class DesignationEqualChoiceRequest(BaseModel):
    occupied_id: int
    decision: str
    expected_versions: dict[str, int]
    confirmed: bool
    idempotency_key: str = Field(min_length=1, max_length=120)


class DesignationAvailableItemRead(BaseModel):
    id: int
    serial_number: str
    source_label: str
    expires_at: datetime
    status: str


class DesignationConflictRead(BaseModel):
    id: int
    designation_type: str
    version: int
    priority: int


class DesignationHistoryRead(BaseModel):
    event: str
    at: datetime
    from_status: str | None
    to_status: str | None
    item_id: int | None = None
    conflict_designation_id: int | None = None
    note: str | None = None
    operator_user_id: int


class DesignationReviewRead(BaseModel):
    id: int
    version: int
    usage_type: str | None
    lifecycle_status: str | None
    verification_status: str | None
    failure_reason: str | None
    verification_note: str | None
    verified_at: datetime | None
    verified_by: int | None
    verifier_name: str | None
    performance_id: int | None
    performance_label: str | None
    beneficiary_performance_player_id: int | None
    beneficiary_player_id: int | None
    beneficiary_name: str
    owner_player_id: int | None
    owner_name: str | None
    designation_type: str
    priority: int
    actor_id: int
    actor_name: str
    role_id: int
    role_name: str
    entitlement_item_id: int | None
    entitlement_serial: str | None
    entitlement_source: str | None
    entitlement_expiry: datetime | None
    available_items: list[DesignationAvailableItemRead]
    conflict: DesignationConflictRead | None
    comparison: str | None
    outcome: str
    action: str
    status_history: list[DesignationHistoryRead]


class WishCreateRequest(BaseModel):
    performance_id: int
    performance_player_id: int
    actor_id: int
    role_id: int
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int = 0
    idempotency_key: str = Field(min_length=1, max_length=120)


class WishCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason_required")
        return value.strip()


class WishUpdateRequest(BaseModel):
    actor_id: int
    role_id: int
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)


class WishAcceptRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int
    idempotency_key: str = Field(min_length=1, max_length=120)


class WishReviewRead(BaseModel):
    id: int
    performance_id: int
    performance_player_id: int
    player_name: str
    actor_id: int
    actor_name: str
    role_id: int
    role_name: str
    note: str | None
    status: str
    failure_reason: str | None
    version: int
