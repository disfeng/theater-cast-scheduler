from datetime import date, datetime, time

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    Wish,
)
from app.models.enums import DesignationType
from app.services.designation_workspace import get_month_workspace, project_designation_conflicts


def _seed_month_workspace(db_session):
    first_theater = Theater(name="西安幽州剧场")
    second_theater = Theater(name="其他剧场")
    first_slot = TheaterSlot(theater=first_theater, name="早场", start_time=time(12, 30))
    second_slot = TheaterSlot(theater=second_theater, name="晚场", start_time=time(19, 30))
    role = Role(theater=first_theater, name="长离", group_name="女")
    actor = Actor(display_name="小展")
    august_first = Performance(
        theater=first_theater,
        theater_slot=first_slot,
        performance_date=date(2026, 8, 1),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    august_second = Performance(
        theater=first_theater,
        theater_slot=first_slot,
        performance_date=date(2026, 8, 2),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    july = Performance(
        theater=first_theater,
        theater_slot=first_slot,
        performance_date=date(2026, 7, 31),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    other = Performance(
        theater=second_theater,
        theater_slot=second_slot,
        performance_date=date(2026, 8, 1),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    db_session.add_all(
        [first_theater, second_theater, first_slot, second_slot, role, actor,
         august_first, august_second, july, other]
    )
    db_session.flush()
    db_session.add_all(
        [
            Designation(
                designation_type=DesignationType.UNIVERSAL,
                player_name="Jennifer",
                role_id=role.id,
                actor_id=actor.id,
                target_performance_id=august_first.id,
                performance_id=august_first.id,
                submitted_at=datetime(2026, 7, 17),
                lifecycle_status="draft",
            ),
            Designation(
                designation_type=DesignationType.TOP_THREE,
                player_name="Kiki",
                role_id=role.id,
                actor_id=actor.id,
                target_performance_id=august_second.id,
                performance_id=august_second.id,
                submitted_at=datetime(2026, 7, 17),
                lifecycle_status="predesignated",
            ),
            Designation(
                designation_type=DesignationType.PAIRED,
                player_name="跨月数据",
                role_id=role.id,
                actor_id=actor.id,
                target_performance_id=july.id,
                performance_id=july.id,
                submitted_at=datetime(2026, 7, 17),
                lifecycle_status="draft",
            ),
            Wish(
                player_name="Sunny",
                role_id=role.id,
                actor_id=actor.id,
                performance_id=august_first.id,
                status="active",
            ),
        ]
    )
    db_session.commit()
    return first_theater


def test_month_workspace_groups_only_requested_theater_and_month(db_session):
    theater = _seed_month_workspace(db_session)

    result = get_month_workspace(db_session, theater.id, 2026, 8)

    assert [day.date.isoformat() for day in result.days] == ["2026-08-01", "2026-08-02"]
    assert result.totals.designations == 2
    assert result.totals.wishes == 1
    assert result.totals.pending == 2
    assert result.days[0].performances[0].totals.designations == 1
    assert result.days[0].performances[0].totals.wishes == 1


def test_month_workspace_returns_empty_days_for_existing_theater(db_session):
    theater = Theater(name="暂无演出的剧场")
    db_session.add(theater)
    db_session.commit()

    result = get_month_workspace(db_session, theater.id, 2026, 8)

    assert result.days == []
    assert result.totals == result.totals.model_copy(update={})


def test_designation_conflicts_mark_only_third_and_fourth_across_year_boundary(db_session):
    theater = Theater(name="跨年剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    role = Role(theater=theater, name="北恒", group_name="男")
    actor = Actor(display_name="子言", max_consecutive_performances=3)
    dates = [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2)]
    performances = [
        Performance(
            theater=theater,
            theater_slot=slot,
            performance_date=day,
            slot_name_snapshot="晚场",
            start_time_snapshot=time(19, 30),
        )
        for day in dates
    ]
    db_session.add_all([role, actor, *performances])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    designations = [
        Designation(
            designation_type=DesignationType.UNIVERSAL,
            player_name=f"玩家{index}",
            role_id=role.id,
            actor_id=actor.id,
            target_performance_id=performance.id,
            performance_id=performance.id,
            submitted_at=datetime(2026, 12, 1),
            lifecycle_status="predesignated" if index < 3 else "draft",
        )
        for index, performance in enumerate(performances)
    ]
    db_session.add_all(designations)
    db_session.commit()

    third = project_designation_conflicts(db_session, designations[2])
    fourth = project_designation_conflicts(db_session, designations[3])

    assert [(row.code, row.severity) for row in third] == [
        ("MAX_CONSECUTIVE_REACHED", "warning")
    ]
    assert ("MAX_CONSECUTIVE_EXCEEDED", "hard") in {
        (row.code, row.severity) for row in fourth
    }
