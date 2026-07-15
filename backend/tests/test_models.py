from datetime import date, time

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Performance,
    Role,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    TheaterWeeklyTemplateEntry,
    WeeklyBatch,
)


def test_actor_can_have_multiple_role_capabilities(db_session):
    actor = Actor(display_name="小展", max_consecutive_performances=3)
    theater_a = Theater(name="西幽剧场")
    theater_b = Theater(name="东幽剧场")
    db_session.add_all([actor, theater_a, theater_b])
    db_session.flush()
    role_a = Role(theater_id=theater_a.id, name="长离", group_name="女位")
    role_b = Role(theater_id=theater_b.id, name="长离", group_name="女位")
    db_session.add_all([role_a, role_b])
    db_session.flush()

    db_session.add_all([
        ActorRoleCapability(actor_id=actor.id, role_id=role_a.id),
        ActorRoleCapability(actor_id=actor.id, role_id=role_b.id),
    ])
    db_session.commit()

    refreshed = db_session.get(Actor, actor.id)
    assert {(cap.role.theater_id, cap.role.name) for cap in refreshed.role_capabilities} == {
        (theater_a.id, "长离"),
        (theater_b.id, "长离"),
    }


def test_theater_supports_ordered_slots_and_relational_weekly_template(db_session):
    theater = Theater(name="西幽剧场")
    db_session.add(theater)
    db_session.flush()
    slots = [
        TheaterSlot(theater_id=theater.id, name="午场", start_time=time(13), sort_order=1),
        TheaterSlot(theater_id=theater.id, name="下午场", start_time=time(16), sort_order=2),
        TheaterSlot(theater_id=theater.id, name="晚场", start_time=time(19), sort_order=3),
        TheaterSlot(theater_id=theater.id, name="夜场", start_time=time(21, 30), sort_order=4),
    ]
    db_session.add_all(slots)
    db_session.flush()
    db_session.add_all([
        TheaterWeeklyTemplateEntry(theater_id=theater.id, weekday="monday", theater_slot_id=slot.id)
        for slot in slots
    ])
    db_session.commit()

    refreshed = db_session.get(Theater, theater.id)
    assert refreshed.name == "西幽剧场"
    assert [slot.name for slot in refreshed.slots] == ["午场", "下午场", "晚场", "夜场"]
    assert len(refreshed.weekly_template_entries) == 4


def test_weekly_batch_owns_versioned_assignment_conflicts(db_session):
    theater = Theater(name="西安幽州剧场")
    actor = Actor(display_name="小展")
    db_session.add_all([theater, actor])
    db_session.flush()
    slot = TheaterSlot(theater_id=theater.id, name="早场", start_time=time(12, 30), sort_order=0)
    role = Role(theater_id=theater.id, name="柳知雨")
    db_session.add_all([slot, role])
    db_session.flush()
    performance = Performance(
        theater_id=theater.id,
        theater_slot_id=slot.id,
        performance_date=date(2026, 12, 28),
        slot_name_snapshot=slot.name,
        start_time_snapshot=slot.start_time,
    )
    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 12, 28))
    db_session.add_all([performance, batch])
    db_session.flush()
    assignment = ScheduleAssignment(
        weekly_batch_id=batch.id,
        performance_id=performance.id,
        role_id=role.id,
        actor_id=actor.id,
        source="manual",
        conflict_codes=["actor_on_leave"],
        requires_approval=True,
        approved=True,
    )
    db_session.add(assignment)
    db_session.commit()

    assert assignment.weekly_batch_id == batch.id
    assert assignment.conflict_codes == ["actor_on_leave"]
    assert batch.version == 1
    assert batch.updated_at is not None
    assert batch.published_at is None
