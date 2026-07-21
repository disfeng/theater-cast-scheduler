from datetime import date, datetime, time

from pydantic import BaseModel, Field


class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class ActorPasswordResetInput(BaseModel):
    entry_theater_id: int


class ActorProfileTheater(BaseModel):
    id: int
    name: str
    is_entry_theater: bool


class ActorProfileRead(BaseModel):
    id: int
    display_name: str
    phone_number: str
    must_change_password: bool
    theaters: list[ActorProfileTheater]


class ActorPerformanceRead(BaseModel):
    notification_id: int
    theater_id: int
    theater_name: str
    performance_id: int
    performance_date: date
    slot_name: str
    start_time: time
    role_name: str
    player_name: str | None
    designation_type: str | None
    designation_label: str | None
    read_at: datetime | None


class ActorCalendarRead(BaseModel):
    month: str
    performances: list[ActorPerformanceRead]


class ActorDashboardRead(BaseModel):
    unread_count: int
    upcoming: list[ActorPerformanceRead]


class LeaveApplicationCreate(BaseModel):
    theater_id: int
    dates: list[date]
    note: str | None = Field(default=None, max_length=500)


class LeaveApplicationDayRead(BaseModel):
    id: int
    leave_date: date
    status: str
    has_schedule_conflict: bool
    review_reason: str | None
    reviewed_at: datetime | None
    withdrawn_at: datetime | None


class LeaveApplicationRead(BaseModel):
    id: int
    actor_id: int
    actor_name: str
    theater_id: int
    theater_name: str
    note: str | None
    created_at: datetime
    days: list[LeaveApplicationDayRead]


class LeaveDayReviewInput(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=500)


class LeavePendingReviewInput(LeaveDayReviewInput):
    pass
