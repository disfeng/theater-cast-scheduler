from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import LeaveStatus, PerformanceStatus, RatingLevel

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
Slot = Literal["early", "late"]


class TheaterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    default_weekly_template: dict[Weekday, list[Slot]]

    @field_validator("default_weekly_template")
    @classmethod
    def reject_duplicate_slots(cls, template: dict[Weekday, list[Slot]]):
        if any(len(slots) != len(set(slots)) for slots in template.values()):
            raise ValueError("weekly_template_has_duplicate_slots")
        return template


class TheaterRead(TheaterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_name: str | None = None


class RoleRead(RoleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


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


class PerformanceRead(BaseModel):
    id: int
    theater_id: int
    performance_date: date
    slot: str
    status: PerformanceStatus


class PerformanceCreate(BaseModel):
    theater_id: int
    performance_date: date
    slot: str


class DashboardRead(BaseModel):
    pending_leave_requests: int
    pending_designations: int
    approval_required_assignments: int
    unpublished_performances: int
