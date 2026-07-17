from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    User,
    Wish,
    WishLifecycleEvent,
)
from app.models.enums import UserRole
from app.schemas.performance_boards import DesignationCancelRequest, WishCancelRequest
from app.services.auth import create_access_token


@pytest.mark.parametrize("schema", [DesignationCancelRequest, WishCancelRequest])
def test_rejection_requests_reject_whitespace_only_reason(schema):
    with pytest.raises(ValidationError):
        schema(reason="   ", expected_version=1, idempotency_key="reject-1")


def test_admin_can_update_and_accept_wish_with_audit(db_session):
    theater = Theater(name="许愿审核剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 8, 5),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    role = Role(theater=theater, name="柳知雨")
    actor = Actor(display_name="vv")
    user = User(email="wish-review@example.com", password_hash="x", role=UserRole.ADMIN)
    db_session.add_all([performance, role, actor, user])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    wish = Wish(
        player_name="Sunny",
        performance_id=performance.id,
        performance_player_id=1,
        actor_id=actor.id,
        role_id=role.id,
        note="原备注",
        status="active",
        version=1,
        active_scope_key="review-wish-scope",
    )
    db_session.add(wish)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(user.email, 'admin')}"}
    try:
        updated = client.patch(
            f"/admin/wishes/{wish.id}",
            headers=headers,
            json={
                "actor_id": actor.id,
                "role_id": role.id,
                "note": "通知当场演员",
                "expected_version": 1,
                "idempotency_key": "wish-update-1",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["note"] == "通知当场演员"
        assert updated.json()["version"] == 2

        accepted = client.post(
            f"/admin/wishes/{wish.id}/accept",
            headers=headers,
            json={
                "note": "客服确认接受",
                "expected_version": 2,
                "idempotency_key": "wish-accept-1",
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        assert accepted.json()["version"] == 3
        assert [row.action for row in db_session.query(WishLifecycleEvent).order_by(WishLifecycleEvent.id)] == [
            "update",
            "accept",
        ]
    finally:
        app.dependency_overrides.clear()
