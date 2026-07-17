from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.performance_boards import DesignationReviewRead, WishReviewRead


class MonthWorkspaceQuery(BaseModel):
    theater_id: int = Field(gt=0)
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


class WorkspaceTotals(BaseModel):
    players: int = Field(default=0, ge=0)
    designations: int = Field(default=0, ge=0)
    wishes: int = Field(default=0, ge=0)
    pending: int = Field(default=0, ge=0)
    conflicts: int = Field(default=0, ge=0)


class DesignationConflictProjection(BaseModel):
    code: str
    severity: Literal["warning", "hard"]
    message: str
    designation_id: int | None = None


class PerformanceSummary(BaseModel):
    id: int
    performance_date: date
    slot_name: str
    start_time: time
    status: str
    totals: WorkspaceTotals


class WorkspaceDay(BaseModel):
    date: date
    performances: list[PerformanceSummary]


class DesignationMonthWorkspaceRead(BaseModel):
    theater_id: int
    year: int
    month: int
    totals: WorkspaceTotals
    days: list[WorkspaceDay]


class PerformancePlayerWorkspaceRead(BaseModel):
    id: int
    player_id: int | None
    player_name: str
    theater_visit_count: int | None = None
    role_visit_count: int | None = None
    role_id: int | None = None
    role_name: str | None = None
    status: str


class PerformanceWorkspaceHeader(BaseModel):
    id: int
    theater_id: int
    theater_name: str
    performance_date: date
    slot_name: str
    start_time: time
    status: str
    totals: WorkspaceTotals


class PerformanceWorkspaceRead(BaseModel):
    performance: PerformanceWorkspaceHeader
    players: list[PerformancePlayerWorkspaceRead]
    designations: list[DesignationReviewRead]
    wishes: list[WishReviewRead]
    conflicts: list[DesignationConflictProjection]
