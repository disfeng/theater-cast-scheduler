from datetime import date, datetime, time

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models.entities import (
    Actor,
    ActorNotificationTask,
    Performance,
    Role,
    Theater,
    TheaterSlot,
)
from app.models.enums import ActorNotificationTaskStatus, ActorNotificationType
from app.services.sms_notifications import reschedule_pending_tasks_for_theater
from auth_helpers import persisted_admin_headers_from_override


def _headers() -> dict[str, str]:
    return persisted_admin_headers_from_override()


def test_sms_switches_default_off(db_session):
    theater = Theater(name="西安幽州剧场")
    db_session.add(theater)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        with TestClient(app) as client:
            global_settings = client.get(
                "/admin/system-settings/actor-notifications", headers=_headers()
            )
            assert global_settings.status_code == 200
            assert global_settings.json()["sms_enabled"] is False

            theater_settings = client.get(
                f"/admin/theaters/{theater.id}/actor-notification-settings",
                headers=_headers(),
            )
            assert theater_settings.status_code == 200
            assert theater_settings.json() == {
                "reveal_days_before": 1,
                "reveal_time": "21:00:00",
                "sms_enabled": False,
            }
    finally:
        app.dependency_overrides.clear()


def test_sms_secret_is_encrypted_and_never_returned(db_session, monkeypatch):
    monkeypatch.setattr(settings, "settings_encryption_key", "sms-test-encryption-key")
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    payload = {
        "sms_enabled": False,
        "actor_portal_url": "https://actors.example.com",
        "access_key_id": "test-access-key",
        "access_key_secret": "super-secret-value",
        "sign_name": "剧场通知",
        "template_code": "SMS_123456",
    }
    try:
        with TestClient(app) as client:
            updated = client.put(
                "/admin/system-settings/actor-notifications",
                headers=_headers(),
                json=payload,
            )
            assert updated.status_code == 200
            assert "super-secret-value" not in updated.text
            assert updated.json()["credentials_configured"] is True

            loaded = client.get("/admin/system-settings/actor-notifications", headers=_headers())
            assert "super-secret-value" not in loaded.text
    finally:
        app.dependency_overrides.clear()


def test_theater_disclosure_policy_can_be_updated(db_session):
    theater = Theater(name="西安幽州剧场")
    db_session.add(theater)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        with TestClient(app) as client:
            response = client.put(
                f"/admin/theaters/{theater.id}/actor-notification-settings",
                headers=_headers(),
                json={
                    "reveal_days_before": 2,
                    "reveal_time": "20:30:00",
                    "sms_enabled": True,
                },
            )
            assert response.status_code == 200
            db_session.refresh(theater)
            assert theater.reveal_days_before == 2
            assert theater.reveal_time == time(20, 30)
            assert theater.actor_sms_enabled is True
    finally:
        app.dependency_overrides.clear()


def test_policy_change_reschedules_pending_tasks(db_session):
    theater = Theater(name="西安幽州剧场", reveal_days_before=2, reveal_time=time(20, 30))
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30), sort_order=0)
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 7, 20),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    actor = Actor(display_name="小A")
    role = Role(theater=theater, name="林月棠")
    db_session.add_all([performance, actor, role])
    db_session.flush()
    task = ActorNotificationTask(
        theater_id=theater.id,
        performance_id=performance.id,
        role_id=role.id,
        actor_id=actor.id,
        schedule_version=1,
        notification_type=ActorNotificationType.NEW_ASSIGNMENT,
        reveal_at=datetime(2026, 7, 19, 21, 0),
        status=ActorNotificationTaskStatus.PENDING,
        assignment_fingerprint="fingerprint",
        idempotency_key="task-1",
    )
    db_session.add(task)
    db_session.flush()

    changed = reschedule_pending_tasks_for_theater(
        db_session, theater.id, now=datetime(2026, 7, 1, 12, 0)
    )

    assert changed == 1
    assert task.reveal_at == datetime(2026, 7, 18, 20, 30)
