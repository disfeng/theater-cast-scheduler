from datetime import date, datetime, time

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorNotification,
    ActorNotificationTask,
    Designation,
    Performance,
    PerformancePlayer,
    Role,
    Theater,
    TheaterSlot,
)
from app.models.enums import (
    ActorNotificationTaskStatus,
    ActorNotificationType,
    DesignationType,
)
from app.services.actor_notifications import reveal_due_tasks
from app.services.auth import create_access_token


def _seed_task(db_session, *, reveal_at: datetime):
    theater = Theater(name="西安幽州剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 7, 20),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    actor = Actor(display_name="小A", phone_number="13800000000")
    role = Role(theater=theater, name="林月棠")
    db_session.add_all([performance, actor, role])
    db_session.flush()
    player = PerformancePlayer(
        performance_id=performance.id,
        player_name_snapshot="微醺未醒",
        player_character_name="柳余潮",
        paired_role_name="林月棠",
        source_board_id=1,
        source_revision_id=1,
    )
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="微醺未醒",
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=performance.id,
        performance_id=performance.id,
        submitted_at=datetime(2026, 7, 1),
        lifecycle_status="fulfilled",
    )
    task = ActorNotificationTask(
        theater_id=theater.id,
        performance_id=performance.id,
        role_id=role.id,
        actor_id=actor.id,
        schedule_version=1,
        notification_type=ActorNotificationType.NEW_ASSIGNMENT,
        reveal_at=reveal_at,
        status=ActorNotificationTaskStatus.PENDING,
        assignment_fingerprint="actor-task-fingerprint",
        idempotency_key="actor-task-1",
    )
    db_session.add_all([player, designation, task])
    db_session.flush()
    return task


def test_reveal_due_tasks_does_not_expose_future_task(db_session):
    task = _seed_task(db_session, reveal_at=datetime(2026, 7, 19, 21, 0))

    assert reveal_due_tasks(db_session, now=datetime(2026, 7, 19, 20, 59)) == 0
    assert db_session.query(ActorNotification).count() == 0
    assert task.status == ActorNotificationTaskStatus.PENDING


def test_reveal_due_tasks_creates_immutable_snapshot(db_session):
    task = _seed_task(db_session, reveal_at=datetime(2026, 7, 19, 21, 0))

    assert reveal_due_tasks(db_session, now=datetime(2026, 7, 19, 21, 0)) == 1
    notification = db_session.query(ActorNotification).one()
    assert notification.theater_name_snapshot == "西安幽州剧场"
    assert notification.performance_date_snapshot == date(2026, 7, 20)
    assert notification.slot_name_snapshot == "晚场"
    assert notification.role_name_snapshot == "林月棠"
    assert notification.player_name_snapshot == "微醺未醒"
    assert notification.designation_type_snapshot == "universal"
    assert task.status == ActorNotificationTaskStatus.REVEALED


def test_actor_calendar_only_returns_own_revealed_snapshots(db_session):
    own_task = _seed_task(db_session, reveal_at=datetime(2026, 7, 19, 21, 0))
    reveal_due_tasks(db_session, now=datetime(2026, 7, 19, 21, 0))
    other_actor = Actor(display_name="小B", phone_number="13900000000")
    db_session.add(other_actor)
    db_session.flush()
    own_notification = db_session.query(ActorNotification).one()
    db_session.add(
        ActorNotification(
            task_id=None,
            theater_id=own_notification.theater_id,
            performance_id=own_notification.performance_id,
            role_id=own_notification.role_id,
            actor_id=other_actor.id,
            notification_type=ActorNotificationType.NEW_ASSIGNMENT,
            schedule_version=1,
            theater_name_snapshot="其他剧场",
            performance_date_snapshot=date(2026, 7, 21),
            slot_name_snapshot="午场",
            start_time_snapshot=time(12, 30),
            role_name_snapshot="其他角色",
            player_name_snapshot="其他玩家",
            designation_type_snapshot=None,
            idempotency_key="other-notification",
        )
    )
    db_session.commit()
    token = create_access_token(
        "13800000000", "actor", actor_id=own_task.actor_id, must_change_password=False
    )
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/actor/me/calendar?month=2026-07",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        rows = response.json()["performances"]
        assert len(rows) == 1
        assert rows[0]["theater_name"] == "西安幽州剧场"
        assert rows[0]["player_name"] == "微醺未醒"
        assert rows[0]["designation_label"] == "万能指定"
    finally:
        app.dependency_overrides.clear()


def test_actor_notification_center_filters_unread_and_marks_read(db_session):
    task = _seed_task(db_session, reveal_at=datetime(2026, 7, 19, 21, 0))
    reveal_due_tasks(db_session, now=datetime(2026, 7, 19, 21, 0))
    notification = db_session.query(ActorNotification).one()
    db_session.commit()
    token = create_access_token(
        "13800000000", "actor", actor_id=task.actor_id, must_change_password=False
    )
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/actor/me/notifications?unread_only=true",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            assert [row["notification_id"] for row in response.json()] == [notification.id]

            read_response = client.post(
                f"/actor/me/notifications/{notification.id}/read",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert read_response.status_code == 200

            response = client.get(
                "/actor/me/notifications?unread_only=true",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.json() == []
    finally:
        app.dependency_overrides.clear()
