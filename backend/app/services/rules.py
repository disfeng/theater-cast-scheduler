from datetime import date

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot, RuleViolation


def validate_candidate(
    candidate: AssignmentCandidate,
    existing_assignments: list[AssignmentCandidate],
    approved_leave_dates: dict[int, set[date]],
    actor_role_ids: dict[int, set[int]],
    monthly_counts: dict[int, int],
    low_rating_caps: dict[int, int],
    suspended_actor_ids: set[int] | None = None,
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    suspended_actor_ids = suspended_actor_ids or set()

    if candidate.actor_id in suspended_actor_ids:
        violations.append(RuleViolation("actor_suspended", "演员已暂停排班"))

    if candidate.performance.date in approved_leave_dates.get(candidate.actor_id, set()):
        violations.append(RuleViolation("actor_on_leave", "演员当天已批准请假"))

    if candidate.role_id not in actor_role_ids.get(candidate.actor_id, set()):
        violations.append(RuleViolation("role_not_allowed", "演员不具备该角色能力"))

    for assignment in existing_assignments:
        if (
            assignment.actor_id == candidate.actor_id
            and assignment.performance.id == candidate.performance.id
        ):
            violations.append(RuleViolation("actor_already_in_performance", "演员同场已出演其他角色"))
            break

    cap = low_rating_caps.get(candidate.actor_id)
    if cap is not None and monthly_counts.get(candidate.actor_id, 0) >= cap:
        violations.append(RuleViolation("low_rating_cap_reached", "低评级演员本月已达上限"))

    return violations


def would_exceed_consecutive_limit(
    actor_id: int,
    target_slot: PerformanceSlot,
    existing_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: int,
    ordered_timeline: list[PerformanceSlot] | None = None,
) -> bool:
    return consecutive_limit_state(
        actor_id,
        target_slot,
        existing_slots,
        max_consecutive,
        ordered_timeline,
    ) == "exceeded"


def consecutive_limit_state(
    actor_id: int,
    target_slot: PerformanceSlot,
    existing_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: int,
    ordered_timeline: list[PerformanceSlot] | None = None,
) -> str | None:
    actor_slots = [*existing_slots.get(actor_id, []), target_slot]
    timeline_by_id = {
        slot.id: slot for slot in [*(ordered_timeline or []), *actor_slots]
    }
    timeline = sorted(
        timeline_by_id.values(),
        key=lambda item: (item.date, item.start_time, item.sort_order, item.id),
    )
    index_by_id = {slot.id: index for index, slot in enumerate(timeline)}
    actor_indexes = sorted({index_by_id[slot.id] for slot in actor_slots})
    longest = 0
    current = 0
    previous_index: int | None = None

    for index in actor_indexes:
        if previous_index is None or index == previous_index + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous_index = index

    if longest > max_consecutive:
        return "exceeded"
    if longest == max_consecutive:
        return "reached"
    return None
