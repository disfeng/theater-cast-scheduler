from datetime import timedelta

from app.core.time import utc_now

from app.models.entities import AuditLog, LoginThrottle, User
from app.models.enums import UserRole
from app.services.login_protection import (
    clear_login_failures,
    record_login_failure,
    record_throttle_failure,
)
from app.services.actor_accounts import password_context
from app.services.auth import create_access_token
from app.api.deps import get_db
from app.main import app
from fastapi.testclient import TestClient


def test_login_failures_lock_account_at_threshold(db_session):
    user = User(email="manager@test", password_hash="x", role=UserRole.THEATER_ADMIN)
    db_session.add(user)
    db_session.flush()
    for _ in range(4):
        assert record_login_failure(user, max_failures=5, lock_minutes=15) is False
    assert record_login_failure(user, max_failures=5, lock_minutes=15) is True
    assert user.failed_login_count == 5
    assert user.locked_until is not None and user.locked_until > utc_now()


def test_successful_login_clears_failure_state(db_session):
    user = User(
        email="manager@test",
        password_hash="x",
        role=UserRole.THEATER_ADMIN,
        failed_login_count=3,
        last_failed_login_at=utc_now(),
        locked_until=utc_now() + timedelta(minutes=5),
    )
    clear_login_failures(user)
    assert user.failed_login_count == 0
    assert user.last_failed_login_at is None
    assert user.locked_until is None


def test_password_reset_invalidates_existing_token(db_session):
    user = User(
        email="manager@test",
        password_hash=password_context.hash("old-password"),
        role=UserRole.THEATER_ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(
        user.email, user.role.value, user_id=user.id, token_version=user.token_version
    )
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        client = TestClient(app)
        assert (
            client.get("/admin/theaters", headers={"Authorization": f"Bearer {token}"}).status_code
            == 200
        )
        user.token_version += 1
        db_session.commit()
        assert (
            client.get("/admin/theaters", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )
    finally:
        app.dependency_overrides.clear()


def test_login_locks_existing_account_and_keeps_generic_response(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_max_failures", 2)
    user = User(
        email="manager@test",
        password_hash=password_context.hash("correct-password"),
        role=UserRole.THEATER_ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        client = TestClient(app)
        for identifier in ("manager@test", "manager@test", "missing@test"):
            response = client.post(
                "/auth/login", json={"identifier": identifier, "password": "wrong"}
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid credentials"
        db_session.refresh(user)
        assert user.locked_until is not None
        assert db_session.query(LoginThrottle).count() == 2
    finally:
        app.dependency_overrides.clear()


def test_locked_identifier_bucket_does_not_extend_on_repeated_attempt(db_session):
    first = record_throttle_failure(
        db_session, "manager@test", "127.0.0.1", max_failures=1, lock_minutes=15
    )
    original_deadline = first.locked_until
    second = record_throttle_failure(
        db_session, "manager@test", "127.0.0.1", max_failures=1, lock_minutes=15
    )
    assert second.failed_count == 1
    assert second.locked_until == original_deadline


def test_actor_login_success_is_audited(db_session):
    user = User(
        email="13800138000",
        password_hash=password_context.hash("correct-password"),
        role=UserRole.ACTOR,
    )
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        response = TestClient(app).post(
            "/auth/login",
            json={"identifier": user.email, "password": "correct-password"},
        )
        assert response.status_code == 200
        audit = db_session.query(AuditLog).filter_by(action="login").one()
        assert audit.operator_user_id == user.id
        assert audit.result.value == "success"
    finally:
        app.dependency_overrides.clear()
