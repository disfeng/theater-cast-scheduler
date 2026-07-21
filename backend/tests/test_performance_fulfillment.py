from datetime import date, datetime, time

from app.models.entities import (
    Actor,
    Designation,
    DesignationLifecycleEvent,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    User,
    Wish,
    WishLifecycleEvent,
)
from app.models.enums import DesignationType, UserRole
from app.services.performance_fulfillment import fulfill_ended_performance


def test_ended_performance_fulfills_effective_designations_and_wishes_once(db_session):
    theater = Theater(name="履约测试剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 7, 19),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    actor = Actor(display_name="小A")
    role = Role(theater=theater, name="林月棠")
    operator = User(email="fulfillment@example.com", password_hash="x", role=UserRole.ADMIN)
    db_session.add_all([performance, actor, role, operator])
    db_session.flush()
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="微醺",
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=performance.id,
        performance_id=performance.id,
        submitted_at=datetime(2026, 7, 1, 12, 0),
        lifecycle_status="effective",
        version=1,
    )
    wish = Wish(
        player_name="微醺",
        role_id=role.id,
        actor_id=actor.id,
        performance_id=performance.id,
        status="effective",
        version=1,
        active_scope_key="fulfill-wish",
    )
    db_session.add_all([designation, wish])
    db_session.commit()

    first = fulfill_ended_performance(
        db_session,
        performance.id,
        operator.id,
        now=datetime(2026, 7, 20, 0, 0),
        idempotency_key="performance-end-1",
    )
    second = fulfill_ended_performance(
        db_session,
        performance.id,
        operator.id,
        now=datetime(2026, 7, 20, 0, 0),
        idempotency_key="performance-end-1",
    )

    assert first == {"designations": 1, "wishes": 1}
    assert second == {"designations": 0, "wishes": 0}
    assert db_session.get(Designation, designation.id).lifecycle_status == "fulfilled"
    assert db_session.get(Wish, wish.id).status == "fulfilled"
    assert [e.action for e in db_session.query(DesignationLifecycleEvent)] == [
        "performance_fulfilled"
    ]
    assert [e.action for e in db_session.query(WishLifecycleEvent)] == [
        "performance_fulfilled"
    ]

