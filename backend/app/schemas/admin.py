from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import LeaveStatus, PerformanceStatus, RatingLevel

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class TheaterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TheaterUpdate(TheaterCreate):
    pass


class TheaterRead(TheaterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class TheaterSlotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_time: time
    sort_order: int = Field(default=0, ge=0)


class TheaterSlotUpdate(TheaterSlotCreate):
    pass


class TheaterSlotRead(TheaterSlotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    theater_id: int
    is_active: bool


class WeeklyTemplateUpdate(BaseModel):
    template: dict[Weekday, list[int]]

    @field_validator("template")
    @classmethod
    def reject_duplicate_slots(cls, template: dict[Weekday, list[int]]):
        if any(len(slots) != len(set(slots)) for slots in template.values()):
            raise ValueError("weekly_template_has_duplicate_slots")
        return template


class RoleCreate(BaseModel):
    theater_id: int
    name: str = Field(min_length=1, max_length=120)
    group_name: str | None = None


class RoleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_name: str | None = None


class RoleRead(RoleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class ActorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    max_consecutive_performances: int = Field(default=3, ge=1, le=3)
    rating_level: RatingLevel = RatingLevel.NORMAL
    low_rating_monthly_cap: int | None = Field(default=None, ge=0)
    notes: str | None = None


class ActorUpdate(BaseModel):
    max_consecutive_performances: int = Field(ge=1, le=3)
    rating_level: RatingLevel
    low_rating_monthly_cap: int | None = Field(default=None, ge=0)
    notes: str | None = None


class CapabilityUpdate(BaseModel):
    role_ids: list[int]


class ActorRead(BaseModel):
    id: int
    display_name: str
    max_consecutive_performances: int
    rating_level: RatingLevel
    low_rating_monthly_cap: int | None
    notes: str | None
    role_ids: list[int]


class LeaveReviewInput(BaseModel):
    status: LeaveStatus


class LeaveRead(BaseModel):
    id: int
    actor_id: int
    actor_name: str
    leave_date: date
    status: LeaveStatus
    note: str | None


class MonthlyPlanRequest(BaseModel):
    theater_id: int
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    closed_dates: list[date] = []


class MonthlyCalendarDay(BaseModel):
    performance_date: date
    theater_slot_ids: list[int]

    @field_validator("theater_slot_ids")
    @classmethod
    def reject_duplicate_slots(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate_theater_slot")
        return value


class MonthlyCalendarReplace(BaseModel):
    theater_id: int
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    days: list[MonthlyCalendarDay]

    @field_validator("days")
    @classmethod
    def reject_duplicate_dates(cls, value: list[MonthlyCalendarDay]) -> list[MonthlyCalendarDay]:
        dates = [item.performance_date for item in value]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate_performance_date")
        return value


class PerformanceRead(BaseModel):
    id: int
    theater_id: int
    theater_slot_id: int
    performance_date: date
    slot_name_snapshot: str
    start_time_snapshot: time
    status: PerformanceStatus


class PerformanceCreate(BaseModel):
    theater_id: int
    theater_slot_id: int
    performance_date: date


class PerformanceUpdate(BaseModel):
    theater_slot_id: int | None = None
    performance_date: date | None = None


class DashboardRead(BaseModel):
    pending_leave_requests: int
    pending_designations: int
    approval_required_assignments: int
    unpublished_performances: int
