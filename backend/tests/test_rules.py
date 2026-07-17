from datetime import date, time

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot
from app.services.rules import (
    consecutive_limit_state,
    validate_candidate,
    would_exceed_consecutive_limit,
)


def test_candidate_fails_when_actor_is_on_leave():
    candidate = AssignmentCandidate(
        actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early")
    )

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={1: {date(2026, 6, 5)}},
        actor_role_ids={1: {10}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["actor_on_leave"]


def test_candidate_fails_when_actor_lacks_role_capability():
    candidate = AssignmentCandidate(
        actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early")
    )

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={},
        actor_role_ids={1: {99}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["role_not_allowed"]


def test_candidate_fails_when_actor_is_suspended():
    candidate = AssignmentCandidate(
        actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early")
    )

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={},
        actor_role_ids={1: {10}},
        monthly_counts={},
        low_rating_caps={},
        suspended_actor_ids={1},
    )

    assert [violation.code for violation in violations] == ["actor_suspended"]


def test_same_actor_cannot_take_two_roles_in_same_performance():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=performance)
    existing = [AssignmentCandidate(actor_id=1, role_id=11, performance=performance)]

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=existing,
        approved_leave_dates={},
        actor_role_ids={1: {10, 11}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["actor_already_in_performance"]


def test_consecutive_limit_detects_fourth_link():
    existing_slots = [
        PerformanceSlot(1, date(2026, 6, 5), "early"),
        PerformanceSlot(2, date(2026, 6, 5), "late"),
        PerformanceSlot(3, date(2026, 6, 6), "early"),
    ]
    target = PerformanceSlot(4, date(2026, 6, 6), "late")

    assert would_exceed_consecutive_limit(1, target, {1: existing_slots}, max_consecutive=3)


def test_consecutive_limit_reports_reached_before_exceeded():
    timeline = [
        PerformanceSlot(
            index, date(2026, 8, 7 + index // 2), f"slot-{index}", time(12 + index * 2), index
        )
        for index in range(4)
    ]

    assert consecutive_limit_state(1, timeline[2], {1: timeline[:2]}, 3, timeline) == "reached"
    assert consecutive_limit_state(1, timeline[3], {1: timeline[:3]}, 3, timeline) == "exceeded"


def test_consecutive_limit_does_not_leak_an_earlier_streak_to_a_disconnected_target():
    timeline = [
        PerformanceSlot(index, date(2026, 8, 1 + index), f"slot-{index}", time(12), index)
        for index in range(5)
    ]

    assert (
        consecutive_limit_state(
            1,
            timeline[4],
            {1: timeline[:3]},
            3,
            timeline,
        )
        is None
    )


def test_consecutive_limit_uses_full_four_slot_timeline_and_resets_on_gap():
    timeline = [
        PerformanceSlot(1, date(2026, 7, 18), "早场", time(10), 0),
        PerformanceSlot(2, date(2026, 7, 18), "午场", time(13), 1),
        PerformanceSlot(3, date(2026, 7, 18), "晚场", time(19), 2),
        PerformanceSlot(4, date(2026, 7, 18), "夜场", time(22), 3),
    ]

    assert would_exceed_consecutive_limit(
        1, timeline[2], {1: [timeline[0], timeline[1]]}, 2, ordered_timeline=timeline
    )
    assert not would_exceed_consecutive_limit(
        1, timeline[2], {1: [timeline[0]]}, 2, ordered_timeline=timeline
    )


def test_consecutive_limit_crosses_week_and_year_boundaries():
    cross_week = [
        PerformanceSlot(1, date(2026, 7, 19), "晚场", time(19), 2),
        PerformanceSlot(2, date(2026, 7, 20), "早场", time(12), 0),
    ]
    cross_year = [
        PerformanceSlot(3, date(2026, 12, 31), "晚场", time(19), 2),
        PerformanceSlot(4, date(2027, 1, 1), "早场", time(12), 0),
    ]

    assert would_exceed_consecutive_limit(
        1, cross_week[1], {1: [cross_week[0]]}, 1, ordered_timeline=cross_week
    )
    assert would_exceed_consecutive_limit(
        1, cross_year[1], {1: [cross_year[0]]}, 1, ordered_timeline=cross_year
    )
