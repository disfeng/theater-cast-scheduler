from datetime import date

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot, RuleViolation


SLOT_ORDER = {"early": 0, "late": 1}


def validate_candidate(
    candidate: AssignmentCandidate,
    existing_assignments: list[AssignmentCandidate],
    approved_leave_dates: dict[int, set[date]],
    actor_role_ids: dict[int, set[int]],
    monthly_counts: dict[int, int],
    low_rating_caps: dict[int, int],
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []

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
) -> bool:
    actor_slots = sorted(
        [*existing_slots.get(actor_id, []), target_slot],
        key=lambda item: (item.date, SLOT_ORDER[item.slot]),
    )
    longest = 0
    current = 0
    previous: PerformanceSlot | None = None

    for slot in actor_slots:
        if previous is None or _is_next_consecutive(previous, slot):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = slot

    return longest > max_consecutive


def _is_next_consecutive(previous: PerformanceSlot, current: PerformanceSlot) -> bool:
    if previous.date == current.date:
        return previous.slot == "early" and current.slot == "late"
    if (current.date - previous.date).days == 1:
        return previous.slot == "late" and current.slot == "early"
    return False
