from datetime import date, datetime

from app.models.enums import DesignationType
from app.schemas.scheduling import DesignationInput, PerformanceSlot, WishInput
from app.schemas.scheduling import AssignmentCandidate
from app.services.scheduler import SchedulingRuleError, generate_week_schedule


def test_scheduler_satisfies_higher_priority_designation_first():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[
            DesignationInput(DesignationType.PAIRED, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)),
            DesignationInput(DesignationType.UNIVERSAL, "玩家B", 10, 2, performance.id, datetime(2026, 6, 1, 13)),
        ],
        wishes=[],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2
    assert result.unsatisfied_designations[0].actor_id == 1


def test_scheduler_uses_wish_only_after_designations():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[],
        wishes=[WishInput("玩家A", 10, 2, "想看2")],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2


def test_scheduler_explains_unsatisfied_designation_on_leave():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={1: {date(2026, 6, 5)}},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[
            DesignationInput(DesignationType.UNIVERSAL, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)),
        ],
        wishes=[],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2
    assert result.unsatisfied_designations[0].failure_reason == "演员当天已批准请假"


def test_scheduler_rejects_locked_assignment_that_violates_hard_rules():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    try:
        generate_week_schedule(
            performances=[performance],
            role_ids=[10],
            actor_ids=[1],
            actor_role_ids={1: {10}},
            max_consecutive={1: 3},
            approved_leave_dates={1: {date(2026, 6, 5)}},
            low_rating_caps={},
            monthly_counts={},
            existing_actor_slots={},
            locked_assignments=[AssignmentCandidate(1, 10, performance)],
            designations=[],
            wishes=[],
        )
    except SchedulingRuleError as exc:
        assert [violation.code for violation in exc.violations] == ["actor_on_leave"]
    else:
        raise AssertionError("Expected locked assignment to be rejected")


def test_scheduler_does_not_assign_suspended_actor():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[],
        wishes=[WishInput("玩家A", 10, 1, "想看暂停演员")],
        suspended_actor_ids={1},
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2
