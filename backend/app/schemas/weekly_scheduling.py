from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AssignmentInput(BaseModel):
    performance_id: int
    role_id: int
    actor_id: int
    source: Literal["manual", "recommended"] = "manual"


class ScheduleWeekContext(BaseModel):
    week_start: date
    assignments: list[AssignmentInput]

    @field_validator("week_start")
    @classmethod
    def monday_only(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start_must_be_monday")
        return value


class MultiWeekValidationRequest(BaseModel):
    theater_id: int
    weeks: list[ScheduleWeekContext]


class ScheduleMutationRequest(BaseModel):
    theater_id: int
    week_start: date
    expected_version: int | None = None
    assignments: list[AssignmentInput]
    context_weeks: list[ScheduleWeekContext] = Field(default_factory=list)
    confirm_conflicts: bool = False
    confirmation_token: str | None = None
    idempotency_key: str | None = None

    @field_validator("week_start")
    @classmethod
    def monday_only(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start_must_be_monday")
        return value


class ScheduleConflictRead(BaseModel):
    code: str
    message: str
    performance_id: int | None = None
    role_id: int | None = None
    actor_id: int | None = None


class PerformanceWorkspaceRead(BaseModel):
    id: int
    performance_date: date
    slot_name: str
    start_time: time
    sort_order: int


class RoleWorkspaceRead(BaseModel):
    id: int
    name: str
    group_name: str | None


class ActorWorkspaceRead(BaseModel):
    id: int
    display_name: str
    rating_level: str
    max_consecutive_performances: int
    low_rating_monthly_cap: int | None
    role_ids: list[int]
    weekly_count: int = 0
    monthly_count: int = 0


class AssignmentRead(AssignmentInput):
    conflict_codes: list[str] = Field(default_factory=list)
    recommendation_reasons: list[str] = Field(default_factory=list)
    locked: bool = False
    designation_id: int | None = None
    designation_type: str | None = None
    owner_player_name: str | None = None
    beneficiary_player_name: str | None = None
    entitlement_serial: str | None = None
    legacy_identity_fallback: bool = False


class WeeklyScheduleWorkspaceRead(BaseModel):
    theater_id: int
    week_start: date
    week_end: date
    batch_id: int | None
    status: str
    version: int
    updated_at: datetime | None
    published_at: datetime | None
    performances: list[PerformanceWorkspaceRead]
    roles: list[RoleWorkspaceRead]
    actors: list[ActorWorkspaceRead]
    assignments: list[AssignmentRead]
    conflicts: list[ScheduleConflictRead]
    conflict_summary: dict[str, int]
    warnings: list[ScheduleConflictRead]
    warning_summary: dict[str, int]
    empty_slots: list[dict[str, int]]
    unsatisfied_designations: list[dict[str, object]] = Field(default_factory=list)
    unsatisfied_wishes: list[dict[str, object]] = Field(default_factory=list)
