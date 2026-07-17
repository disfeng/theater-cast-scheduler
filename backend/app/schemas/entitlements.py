from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
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


class ItemTypeWrite(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)
    priority: int = Field(ge=0)
    default_validity_months: int = Field(gt=0)

    @field_validator("code", "display_name")
    @classmethod
    def valid_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ItemTypeUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    priority: int | None = Field(default=None, ge=0)
    default_validity_months: int | None = Field(default=None, gt=0)

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ItemTypeRead(ItemTypeWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int


class GrantDraftItemWrite(BaseModel):
    player_id: int
    item_type_id: int
    quantity: int = Field(default=1, ge=1)
    source_month: date | None = None
    source_label: str | None = Field(default=None, min_length=1, max_length=120)
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=4000)

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


class GrantBatchCreate(BaseModel):
    source_month: date
    source_label: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    grant_date: date | None = None
    default_expires_at: datetime | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=4000)
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
    source_month: date
    source_label: str
    title: str | None
    grant_date: date | None
    default_expires_at: datetime | None
    notes: str | None
    status: GrantBatchStatus
    created_at: datetime
    confirmed_at: datetime | None
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
    event_type: EntitlementEventType
    occurred_at: datetime
    from_status: EntitlementItemStatus | None
    to_status: EntitlementItemStatus | None
    performance_id: int | None
    designation_id: int | None
    reason: str | None
    operator_user_id: int | None


class EntitlementItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    serial_number: str
    owner_id: int
    item_type_id: int
    source_month: date
    source_label: str
    granted_at: datetime
    expires_at: datetime
    status: EntitlementItemStatus
    current_designation_id: int | None
    notes: str | None
    ledger_entries: list[LedgerRead] = Field(default_factory=list)


class PlayerInventoryRead(BaseModel):
    player: PlayerRead
    items: list[EntitlementItemRead]
