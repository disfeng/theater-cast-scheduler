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
            DesignationInput(
                DesignationType.PAIRED, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)
            ),
            DesignationInput(
                DesignationType.UNIVERSAL, "玩家B", 10, 2, performance.id, datetime(2026, 6, 1, 13)
            ),
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
        wishes=[
            WishInput(
                "玩家A", 10, 2, "想看2", performance_id=performance.id, performance_player_id=7
            )
        ],
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
            DesignationInput(
                DesignationType.UNIVERSAL, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)
            ),
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
        wishes=[
            WishInput(
                "玩家A",
                10,
                1,
                "想看暂停演员",
                performance_id=performance.id,
                performance_player_id=7,
            )
        ],
        suspended_actor_ids={1},
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2


def test_performance_scoped_wish_does_not_leak_to_another_performance():
    first = PerformanceSlot(1, date(2026, 6, 5), "early")
    second = PerformanceSlot(2, date(2026, 6, 6), "early")
    result = generate_week_schedule(
        performances=[first, second],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={1: 1, 2: 0},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[],
        wishes=[WishInput("玩家A", 10, 1, performance_id=second.id, performance_player_id=7)],
    )
    assert result.assignments[(first.id, 10)].actor_id == 2
    assert result.assignments[(second.id, 10)].actor_id == 1


def test_wish_never_overrides_designation_and_reports_stable_unsatisfied_reason():
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
            DesignationInput(
                DesignationType.PAIRED, "D", 10, 2, performance.id, datetime(2026, 6, 1)
            )
        ],
        wishes=[WishInput("W", 10, 1, performance_id=performance.id, performance_player_id=8)],
    )
    assert result.assignments[(performance.id, 10)].actor_id == 2
    assert result.unsatisfied_wishes[0].failure_reason == "role_occupied_by_designation"


def test_wish_cannot_bypass_leave_or_capability_or_consecutive_limit():
    target = PerformanceSlot(2, date(2026, 6, 5), "late")
    prior = PerformanceSlot(1, date(2026, 6, 5), "early")
    common = dict(
        performances=[target],
        role_ids=[10],
        actor_ids=[1, 2],
        max_consecutive={1: 1, 2: 3},
        low_rating_caps={},
        monthly_counts={},
        locked_assignments=[],
        designations=[],
        wishes=[WishInput("W", 10, 1, performance_id=target.id, performance_player_id=8)],
        ordered_timeline=[prior, target],
    )
    leave = generate_week_schedule(
        **common,
        actor_role_ids={1: {10}, 2: {10}},
        approved_leave_dates={1: {target.date}},
        existing_actor_slots={},
    )
    assert leave.assignments[(target.id, 10)].actor_id == 2
    capability = generate_week_schedule(
        **common,
        actor_role_ids={1: set(), 2: {10}},
        approved_leave_dates={},
        existing_actor_slots={},
    )
    assert capability.assignments[(target.id, 10)].actor_id == 2
    consecutive = generate_week_schedule(
        **common,
        actor_role_ids={1: {10}, 2: {10}},
        approved_leave_dates={},
        existing_actor_slots={1: [prior]},
    )
    assert consecutive.assignments[(target.id, 10)].actor_id == 2
    assert all(
        result.unsatisfied_wishes[0].failure_reason == "hard_rules_prevented_match"
        for result in (leave, capability, consecutive)
    )
