from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PerformanceSlot:
    id: int
    date: date
    slot: str


@dataclass(frozen=True)
class AssignmentCandidate:
    actor_id: int
    role_id: int
    performance: PerformanceSlot


@dataclass(frozen=True)
class RuleViolation:
    code: str
    message: str
