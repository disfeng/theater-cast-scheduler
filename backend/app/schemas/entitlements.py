from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    DesignationType,
    EntitlementEventType,
    EntitlementItemCategory,
    EntitlementItemStatus,
    EntitlementSourceType,
    EntitlementGrantMode,
    GrantBatchStatus,
    PlayerStatus,
)


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str
    normalized_name: str
    status: PlayerStatus


class PlayerMatchResult(BaseModel):
    player: PlayerRead | None = None
    candidates: list[PlayerRead] = Field(default_factory=list)
    created: bool = False


class BulkPlayerMatchRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=500)

    @field_validator("names")
    @classmethod
    def clean_names(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            name = value.strip()
            normalized = name.casefold()
            if name and normalized not in seen:
                seen.add(normalized)
                cleaned.append(name)
        if not cleaned:
            raise ValueError("player_names_required")
        return cleaned


class BulkPlayerMatchRead(PlayerMatchResult):
    raw_name: str


class PlayerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PlayerUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    status: PlayerStatus | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=120)

    @field_validator("alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PlayerMergeRequest(BaseModel):
    source_player_id: int


class ItemTypeCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    display_name: str = Field(min_length=1, max_length=120)
    category: EntitlementItemCategory
    designation_type: DesignationType | None = None
    priority: int = Field(default=0, ge=0)
    default_validity_days: int = Field(default=90, ge=1, le=3650)
    color: str = Field(default="#409eff", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)
    binds_beneficiary: bool = False
    binds_actor: bool = False

    @field_validator("code", "display_name")
    @classmethod
    def valid_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def valid_category_binding(self):
        if self.category == EntitlementItemCategory.DESIGNATION and self.designation_type is None:
            raise ValueError("designation_type_required")
        if self.category == EntitlementItemCategory.GENERAL and self.designation_type is not None:
            raise ValueError("general_item_cannot_bind_designation")
        return self


class ItemTypeUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    category: EntitlementItemCategory | None = None
    designation_type: DesignationType | None = None
    priority: int | None = Field(default=None, ge=0)
    default_validity_days: int | None = Field(default=None, ge=1, le=3650)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    binds_beneficiary: bool | None = None
    binds_actor: bool | None = None

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ItemTypeRead(ItemTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int | None
    binding_locked_at: datetime | None


class GrantDraftItemWrite(BaseModel):
    player_id: int
    item_type_id: int
    quantity: int = Field(default=1, ge=1)
    source_month: date | None = None
    source_label: str | None = Field(default=None, min_length=1, max_length=120)
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=4000)
    bound_actor_id: int | None = None

    @field_validator("source_label", "notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class GrantDraftItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    player_id: int
    item_type_id: int
    source_month: date | None
    source_label: str | None
    expires_at: datetime | None
    notes: str | None
    bound_actor_id: int | None


class GrantBatchCreate(BaseModel):
    grant_mode: EntitlementGrantMode = EntitlementGrantMode.BY_PLAYER
    source_type: EntitlementSourceType = EntitlementSourceType.OTHER
    source_month: date | None = None
    source_label: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    grant_date: date | None = None
    default_expires_at: datetime | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=4000)
    bound_actor_id: int | None = None
    items: list[GrantDraftItemWrite] = Field(default_factory=list)

    @field_validator("source_label")
    @classmethod
    def valid_source_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("title", "notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class GrantBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int | None
    grant_mode: EntitlementGrantMode
    source_type: EntitlementSourceType
    source_month: date | None
    source_label: str
    title: str | None
    grant_date: date | None
    default_expires_at: datetime | None
    notes: str | None
    status: GrantBatchStatus
    created_at: datetime
    confirmed_at: datetime | None
    bound_actor_id: int | None
    draft_items: list[GrantDraftItemRead] = Field(default_factory=list)


class ExtensionRequest(BaseModel):
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AdjustmentRequest(BaseModel):
    expires_at: datetime | None = None
    source_label: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("source_label", "notes")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class LedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int | None
    event_type: EntitlementEventType
    occurred_at: datetime
    from_status: EntitlementItemStatus | None
    to_status: EntitlementItemStatus | None
    performance_id: int | None
    designation_id: int | None
    reason: str | None
    purpose: str | None
    operator_user_id: int | None


class EntitlementItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int | None
    serial_number: str
    owner_id: int
    item_type_id: int
    source_type: EntitlementSourceType
    source_month: date | None
    source_label: str
    granted_at: datetime
    expires_at: datetime
    status: EntitlementItemStatus
    current_designation_id: int | None
    notes: str | None
    bound_actor_id: int | None
    bound_actor_name: str | None
    binds_beneficiary_snapshot: bool
    binds_actor_snapshot: bool
    ledger_entries: list[LedgerRead] = Field(default_factory=list)


class PlayerInventoryRead(BaseModel):
    player: PlayerRead
    items: list[EntitlementItemRead]


class PlayerInventorySummaryRead(BaseModel):
    player_id: int
    display_name: str
    normalized_name: str
    sort_key: str
    status: PlayerStatus
    item_count: int
    expired_count: int


class ManualConsumeRequest(BaseModel):
    item_type_id: int
    quantity: int = Field(ge=1, le=100)
    purpose: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=4000)
    performance_id: int | None = None

    @field_validator("purpose", "note")
    @classmethod
    def clean_manual_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ManualConsumeRead(BaseModel):
    item_ids: list[int]
    serial_numbers: list[str]


class EntitlementLedgerRecordRead(BaseModel):
    id: int
    theater_id: int | None
    item_id: int
    serial_number: str
    player_id: int
    player_name: str
    item_type_id: int
    item_type_name: str
    bound_actor_id: int | None
    bound_actor_name: str | None
    event_type: EntitlementEventType
    occurred_at: datetime
    from_status: EntitlementItemStatus | None
    to_status: EntitlementItemStatus | None
    purpose: str | None
    reason: str | None
    note: str | None
    performance_id: int | None
    designation_id: int | None
    operator_user_id: int | None


class EntitlementLedgerPageRead(BaseModel):
    records: list[EntitlementLedgerRecordRead]
    next_cursor: int | None
