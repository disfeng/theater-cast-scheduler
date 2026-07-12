from dataclasses import replace
from datetime import date

from app.models.enums import DesignationType
from app.schemas.scheduling import (
    AssignmentCandidate,
    DesignationInput,
    PerformanceSlot,
    RuleViolation,
    ScheduleResult,
    WishInput,
)
from app.services.rules import validate_candidate, would_exceed_consecutive_limit


DESIGNATION_PRIORITY = {
    DesignationType.UNIVERSAL: 0,
    DesignationType.TOP_THREE: 1,
    DesignationType.PAIRED: 2,
}


def generate_week_schedule(
    performances: list[PerformanceSlot],
    role_ids: list[int],
    actor_ids: list[int],
    actor_role_ids: dict[int, set[int]],
    max_consecutive: dict[int, int],
    approved_leave_dates: dict[int, set[date]],
    low_rating_caps: dict[int, int],
    monthly_counts: dict[int, int],
    existing_actor_slots: dict[int, list[PerformanceSlot]],
    locked_assignments: list[AssignmentCandidate],
    designations: list[DesignationInput],
    wishes: list[WishInput],
) -> ScheduleResult:
    assignments: dict[tuple[int, int], AssignmentCandidate] = {}
    explanations: dict[tuple[int, int, int], list[RuleViolation]] = {}
    unsatisfied_designations: list[DesignationInput] = []
    mutable_monthly_counts = dict(monthly_counts)
    mutable_actor_slots = {actor_id: list(slots) for actor_id, slots in existing_actor_slots.items()}

    for assignment in locked_assignments:
        assignments[(assignment.performance.id, assignment.role_id)] = assignment
        mutable_monthly_counts[assignment.actor_id] = mutable_monthly_counts.get(assignment.actor_id, 0) + 1
        mutable_actor_slots.setdefault(assignment.actor_id, []).append(assignment.performance)

    sorted_designations = sorted(
        designations,
        key=lambda item: (DESIGNATION_PRIORITY[item.designation_type], item.submitted_at),
    )
    performance_by_id = {performance.id: performance for performance in performances}

    for designation in sorted_designations:
        target_performances = (
            [performance_by_id[designation.target_performance_id]]
            if designation.target_performance_id in performance_by_id
            else performances
        )
        placed = False
        last_reason = "没有可用场次"
        for performance in target_performances:
            key = (performance.id, designation.role_id)
            if key in assignments:
                last_reason = "目标槽位已被更高优先级记录占用"
                continue
            candidate = AssignmentCandidate(designation.actor_id, designation.role_id, performance)
            violations = _violations_for_candidate(
                candidate,
                assignments,
                approved_leave_dates,
                actor_role_ids,
                mutable_monthly_counts,
                low_rating_caps,
                mutable_actor_slots,
                max_consecutive,
            )
            explanations[(performance.id, designation.role_id, designation.actor_id)] = violations
            if violations:
                last_reason = violations[0].message
                continue
            _place(candidate, assignments, mutable_monthly_counts, mutable_actor_slots)
            placed = True
            break
        if not placed:
            unsatisfied_designations.append(replace(designation, failure_reason=last_reason))

    for performance in performances:
        for role_id in role_ids:
            key = (performance.id, role_id)
            if key in assignments:
                continue
            best_candidate = _best_candidate(
                performance,
                role_id,
                actor_ids,
                actor_role_ids,
                approved_leave_dates,
                low_rating_caps,
                mutable_monthly_counts,
                mutable_actor_slots,
                max_consecutive,
                assignments,
                wishes,
            )
            if best_candidate is not None:
                _place(best_candidate, assignments, mutable_monthly_counts, mutable_actor_slots)

    empty_slots = [
        (performance.id, role_id)
        for performance in performances
        for role_id in role_ids
        if (performance.id, role_id) not in assignments
    ]
    unsatisfied_wishes = [
        wish
        for wish in wishes
        if not any(
            assignment.role_id == wish.role_id and assignment.actor_id == wish.actor_id
            for assignment in assignments.values()
        )
    ]

    return ScheduleResult(assignments, unsatisfied_designations, unsatisfied_wishes, empty_slots, explanations)


def _best_candidate(
    performance: PerformanceSlot,
    role_id: int,
    actor_ids: list[int],
    actor_role_ids: dict[int, set[int]],
    approved_leave_dates: dict[int, set[date]],
    low_rating_caps: dict[int, int],
    monthly_counts: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: dict[int, int],
    assignments: dict[tuple[int, int], AssignmentCandidate],
    wishes: list[WishInput],
) -> AssignmentCandidate | None:
    valid: list[tuple[int, AssignmentCandidate]] = []
    for actor_id in actor_ids:
        candidate = AssignmentCandidate(actor_id, role_id, performance)
        violations = _violations_for_candidate(
            candidate,
            assignments,
            approved_leave_dates,
            actor_role_ids,
            monthly_counts,
            low_rating_caps,
            actor_slots,
            max_consecutive,
        )
        if violations:
            continue
        wish_score = 100 if any(wish.role_id == role_id and wish.actor_id == actor_id for wish in wishes) else 0
        balance_score = -monthly_counts.get(actor_id, 0)
        valid.append((wish_score + balance_score, candidate))
    if not valid:
        return None
    return sorted(valid, key=lambda item: (-item[0], item[1].actor_id))[0][1]


def _violations_for_candidate(
    candidate: AssignmentCandidate,
    assignments: dict[tuple[int, int], AssignmentCandidate],
    approved_leave_dates: dict[int, set[date]],
    actor_role_ids: dict[int, set[int]],
    monthly_counts: dict[int, int],
    low_rating_caps: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: dict[int, int],
) -> list[RuleViolation]:
    violations = validate_candidate(
        candidate,
        list(assignments.values()),
        approved_leave_dates,
        actor_role_ids,
        monthly_counts,
        low_rating_caps,
    )
    if would_exceed_consecutive_limit(
        candidate.actor_id,
        candidate.performance,
        actor_slots,
        max_consecutive.get(candidate.actor_id, 3),
    ):
        violations.append(RuleViolation("consecutive_limit_exceeded", "超过演员个人最大连场数"))
    return violations


def _place(
    candidate: AssignmentCandidate,
    assignments: dict[tuple[int, int], AssignmentCandidate],
    monthly_counts: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
) -> None:
    assignments[(candidate.performance.id, candidate.role_id)] = candidate
    monthly_counts[candidate.actor_id] = monthly_counts.get(candidate.actor_id, 0) + 1
    actor_slots.setdefault(candidate.actor_id, []).append(candidate.performance)
