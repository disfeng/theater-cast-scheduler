from datetime import date

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot
from app.services.rules import validate_candidate, would_exceed_consecutive_limit


def test_candidate_fails_when_actor_is_on_leave():
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early"))

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
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early"))

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={},
        actor_role_ids={1: {99}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["role_not_allowed"]


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
