from datetime import date, datetime, time

import pytest

from app.models.entities import Actor, Performance, ScheduleAssignment, Theater, TheaterSlot, WeeklyBatch
from app.models.enums import BatchStatus, LeaveStatus
from app.services.actor_leaves import review_leave_day, submit_leave_application, withdraw_leave_day


def test_grouped_leave_supports_partial_daily_review(db_session):
    theater = Theater(name="西安幽州剧场")
    actor = Actor(display_name="小A", phone_number="13800000000")
    db_session.add_all([theater, actor]); db_session.flush()
    application = submit_leave_application(
        db_session, actor.id, theater.id,
        [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)], "家事",
        today=date(2026, 7, 19),
    )
    review_leave_day(db_session, application.days[0].id, LeaveStatus.APPROVED, None, 1)
    review_leave_day(db_session, application.days[1].id, LeaveStatus.REJECTED, "当日必须到场", 1)
    assert [day.status for day in application.days] == [LeaveStatus.APPROVED, LeaveStatus.REJECTED, LeaveStatus.PENDING]
    with pytest.raises(ValueError, match="驳回请填写理由"):
        review_leave_day(db_session, application.days[2].id, LeaveStatus.REJECTED, None, 1)


def test_conflict_marker_contains_no_schedule_details(db_session):
    theater = Theater(name="西安幽州剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    actor = Actor(display_name="小A")
    performance = Performance(theater=theater, theater_slot=slot, performance_date=date(2026, 8, 3), slot_name_snapshot="晚场", start_time_snapshot=time(19, 30))
    batch = WeeklyBatch(theater_id=1, week_start=date(2026, 8, 3), status=BatchStatus.SCHEDULED, created_at=datetime.now())
    db_session.add_all([performance, actor]); db_session.flush(); batch.theater_id = theater.id; db_session.add(batch); db_session.flush()
    db_session.add(ScheduleAssignment(weekly_batch_id=batch.id, performance_id=performance.id, role_id=1, actor_id=actor.id, source="manual")); db_session.flush()
    application = submit_leave_application(db_session, actor.id, theater.id, [date(2026, 8, 3)], None, today=date(2026, 7, 19))
    day = application.days[0]
    assert day.has_schedule_conflict is True
    assert day.conflict_performance_ids == [performance.id]


def test_pending_day_can_be_withdrawn(db_session):
    theater = Theater(name="西安幽州剧场"); actor = Actor(display_name="小A")
    db_session.add_all([theater, actor]); db_session.flush()
    application = submit_leave_application(db_session, actor.id, theater.id, [date(2026, 8, 3)], None, today=date(2026, 7, 19))
    day = withdraw_leave_day(db_session, actor.id, application.days[0].id)
    assert day.withdrawn_at is not None
