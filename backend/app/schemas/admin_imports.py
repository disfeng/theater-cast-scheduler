from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from app.models.enums import BatchStatus, ImportDraftStatus, DraftItemKind, DraftValidationStatus, DesignationType

class WeeklyBatchCreate(BaseModel):
    theater_id: int
    week_start: date


class WeeklyBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int
    week_start: date
    status: BatchStatus
    created_at: datetime


class ImportParseRequest(BaseModel):
    raw_text: str


class DraftItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    import_draft_id: int
    item_kind: DraftItemKind
    raw_line: str | None
    designation_type: DesignationType | None
    player_name: str | None
    actor_name_raw: str | None
    role_name_raw: str | None
    actor_id: int | None
    role_id: int | None
    target_performance_id: int | None
    note: str | None
    validation_status: DraftValidationStatus
    failure_reason: str | None
    confirmed_at: datetime | None
    designation_id: int | None
    wish_id: int | None


class ImportDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    weekly_batch_id: int
    raw_text: str
    status: ImportDraftStatus
    created_at: datetime
    updated_at: datetime
    items: list[DraftItemRead]


class DraftItemCreate(BaseModel):
    item_kind: DraftItemKind
    designation_type: DesignationType | None = None
    player_name: str | None = None
    actor_name_raw: str | None = None
    role_name_raw: str | None = None
    actor_id: int | None = None
    role_id: int | None = None
    target_performance_id: int | None = None
    note: str | None = None


class DraftItemUpdate(BaseModel):
    item_kind: DraftItemKind
    designation_type: DesignationType | None = None
    player_name: str | None = None
    actor_name_raw: str | None = None
    role_name_raw: str | None = None
    actor_id: int | None = None
    role_id: int | None = None
    target_performance_id: int | None = None
    note: str | None = None


class DesignationInputModel(BaseModel):
    designation_type: DesignationType
    player_name: str
    role_id: int
    actor_id: int
    target_performance_id: int | None
    submitted_at: datetime
    failure_reason: str | None = None


class WishInputModel(BaseModel):
    player_name: str
    role_id: int
    actor_id: int
    note: str | None = None


class BatchSchedulingInputs(BaseModel):
    designations: list[DesignationInputModel]
    wishes: list[WishInputModel]
