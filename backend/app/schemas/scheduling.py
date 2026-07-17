from dataclasses import dataclass
from datetime import date, datetime, time
from app.models.enums import DesignationType


@dataclass(frozen=True)
class PerformanceSlot:
    id: int
    date: date
    slot: str
    start_time: time = time.min
    sort_order: int = 0


@dataclass(frozen=True)
class AssignmentCandidate:
    actor_id: int
    role_id: int
    performance: PerformanceSlot


@dataclass(frozen=True)
class RuleViolation:
    code: str
    message: str


@dataclass(frozen=True)
class DesignationInput:
    designation_type: DesignationType
    player_name: str
    role_id: int
    actor_id: int
    target_performance_id: int | None
    submitted_at: datetime
    failure_reason: str | None = None


@dataclass(frozen=True)
class WishInput:
    player_name: str
    role_id: int
    actor_id: int
    note: str | None = None
    performance_id: int | None = None
    performance_player_id: int | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class ScheduleResult:
    assignments: dict[tuple[int, int], AssignmentCandidate]
    unsatisfied_designations: list[DesignationInput]
    unsatisfied_wishes: list[WishInput]
    empty_slots: list[tuple[int, int]]
    explanations: dict[tuple[int, int, int], list[RuleViolation]]
