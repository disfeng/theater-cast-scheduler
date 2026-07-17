from datetime import date, time

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Performance,
    PerformanceBoard,
    PerformanceBoardRevision,
    PerformancePlayer,
    PlayerProfile,
    Role,
    Theater,
    TheaterSlot,
    User,
    Wish,
    WishLifecycleEvent,
)
from app.models.enums import UserRole
from app.services.auth import create_access_token
from app.services.wishes import set_wish_status


def test_admin_can_create_list_and_cancel_concrete_performance_wish(db_session):
    theater = Theater(name="T")
    slot = TheaterSlot(theater=theater, name="night", start_time=time(19))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 8, 1),
        slot_name_snapshot="night",
        start_time_snapshot=time(19),
    )
    player = PlayerProfile(display_name="Sunny", normalized_name="sunny")
    actor = Actor(display_name="Actor")
    role = Role(theater=theater, name="Role")
    db_session.add_all(
        [
            performance,
            player,
            actor,
            role,
            User(email="admin@example.com", password_hash="x", role=UserRole.ADMIN),
        ]
    )
    db_session.flush()
    board = PerformanceBoard(performance_id=performance.id)
    db_session.add(board)
    db_session.flush()
    revision = PerformanceBoardRevision(board_id=board.id, revision_number=1, raw_text="")
    db_session.add(revision)
    db_session.flush()
    performance_player = PerformancePlayer(
        performance_id=performance.id,
        player_profile_id=player.id,
        player_name_snapshot="Sunny",
        player_character_name="sunny",
        paired_role_name="Role",
        source_board_id=board.id,
        source_revision_id=revision.id,
        is_active=True,
    )
    db_session.add_all(
        [performance_player, ActorRoleCapability(actor_id=actor.id, role_id=role.id)]
    )
    db_session.commit()

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('admin@example.com', 'admin')}"}
    try:
        created = client.post(
            "/admin/wishes",
            headers=headers,
            json={
                "performance_id": performance.id,
                "performance_player_id": performance_player.id,
                "actor_id": actor.id,
                "role_id": role.id,
                "note": "please",
                "expected_version": 0,
                "idempotency_key": "create-1",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body | {"status": body["status"]} == body
        assert body["player_name"] == "Sunny"
        assert body["performance_id"] == performance.id
        assert body["performance_player_id"] == performance_player.id
        assert body["status"] == "active"
        assert body["version"] == 1
        replay = client.post(
            "/admin/wishes",
            headers=headers,
            json={
                "performance_id": performance.id,
                "performance_player_id": performance_player.id,
                "actor_id": actor.id,
                "role_id": role.id,
                "note": "please",
                "expected_version": 0,
                "idempotency_key": "create-1",
            },
        )
        assert replay.json() == body
        assert db_session.query(Wish).count() == 1
        conflict = client.post(
            "/admin/wishes",
            headers=headers,
            json={
                "performance_id": performance.id,
                "performance_player_id": performance_player.id,
                "actor_id": actor.id,
                "role_id": role.id,
                "note": "changed",
                "expected_version": 0,
                "idempotency_key": "create-1",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "wish_idempotency_conflict"
        assert client.get(
            f"/admin/wishes?performance_id={performance.id}", headers=headers
        ).json() == [body]
        cancelled = client.post(
            f"/admin/wishes/{body['id']}/cancel",
            headers=headers,
            json={"reason": "duplicate", "expected_version": 1, "idempotency_key": "cancel-1"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["failure_reason"] == "duplicate"
        assert cancelled.json()["version"] == 2
        assert (
            client.post(
                "/admin/wishes",
                headers=headers,
                json={
                    "performance_id": performance.id,
                    "performance_player_id": performance_player.id,
                    "actor_id": actor.id,
                    "role_id": role.id,
                    "note": "please",
                    "expected_version": 0,
                    "idempotency_key": "create-1",
                },
            ).json()
            == body
        )
        live = db_session.get(Wish, body["id"])
        operator = db_session.query(User).filter_by(email="admin@example.com").one()
        set_wish_status(
            db_session,
            live.id,
            "active",
            None,
            operator.id,
            expected_version=live.version,
            idempotency_key="restore-direct",
            action="board_restore",
        )
        db_session.commit()
        cancel_replay = client.post(
            f"/admin/wishes/{body['id']}/cancel",
            headers=headers,
            json={"reason": "duplicate", "expected_version": 1, "idempotency_key": "cancel-1"},
        )
        assert cancel_replay.json() == cancelled.json()
        live = db_session.get(Wish, body["id"])
        set_wish_status(
            db_session,
            live.id,
            "cancelled",
            "cycle complete",
            operator.id,
            expected_version=live.version,
            idempotency_key="remove-direct",
            action="board_remove",
        )
        db_session.commit()
        assert (
            client.post(
                f"/admin/wishes/{body['id']}/cancel",
                headers=headers,
                json={"reason": "duplicate", "expected_version": 1, "idempotency_key": "cancel-1"},
            ).json()
            == cancelled.json()
        )
        stale = client.post(
            f"/admin/wishes/{body['id']}/cancel",
            headers=headers,
            json={"reason": "again", "expected_version": 1, "idempotency_key": "cancel-2"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == "wish_version_conflict"
        second = client.post(
            "/admin/wishes",
            headers=headers,
            json={
                "performance_id": performance.id,
                "performance_player_id": performance_player.id,
                "actor_id": actor.id,
                "role_id": role.id,
                "note": "second cycle",
                "expected_version": 0,
                "idempotency_key": "create-2",
            },
        )
        assert second.status_code == 200
        second_cancel = client.post(
            f"/admin/wishes/{second.json()['id']}/cancel",
            headers=headers,
            json={"reason": "second done", "expected_version": 1, "idempotency_key": "cancel-2b"},
        )
        assert second_cancel.status_code == 200
        assert [
            (event.action, event.from_status, event.to_status)
            for event in db_session.query(WishLifecycleEvent).order_by(WishLifecycleEvent.id)
        ] == [
            ("create", None, "active"),
            ("cancel", "active", "cancelled"),
            ("board_restore", "cancelled", "active"),
            ("board_remove", "active", "cancelled"),
            ("create", None, "active"),
            ("cancel", "active", "cancelled"),
        ]
        assert all(row.weekly_batch_id is None for row in db_session.query(Wish).all())
    finally:
        app.dependency_overrides.clear()


def test_new_wish_rejects_player_from_another_performance_and_incapable_actor(db_session):
    theater = Theater(name="T")
    slot = TheaterSlot(theater=theater, name="night", start_time=time(19))
    performances = [
        Performance(
            theater=theater,
            theater_slot=slot,
            performance_date=date(2026, 8, day),
            slot_name_snapshot="night",
            start_time_snapshot=time(19),
        )
        for day in (1, 2)
    ]
    player = PlayerProfile(display_name="Sunny", normalized_name="sunny")
    actor = Actor(display_name="Actor")
    role = Role(theater=theater, name="Role")
    db_session.add_all(
        [
            *performances,
            player,
            actor,
            role,
            User(email="admin@example.com", password_hash="x", role=UserRole.ADMIN),
        ]
    )
    db_session.flush()
    board = PerformanceBoard(performance_id=performances[1].id)
    db_session.add(board)
    db_session.flush()
    revision = PerformanceBoardRevision(board_id=board.id, revision_number=1, raw_text="")
    db_session.add(revision)
    db_session.flush()
    pp = PerformancePlayer(
        performance_id=performances[1].id,
        player_profile_id=player.id,
        player_name_snapshot="Sunny",
        player_character_name="sunny",
        paired_role_name="Role",
        source_board_id=board.id,
        source_revision_id=revision.id,
        is_active=True,
    )
    db_session.add(pp)
    db_session.commit()

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('admin@example.com', 'admin')}"}
    try:
        payload = {
            "performance_id": performances[0].id,
            "performance_player_id": pp.id,
            "actor_id": actor.id,
            "role_id": role.id,
            "expected_version": 0,
            "idempotency_key": "create-bad",
        }
        assert (
            client.post("/admin/wishes", headers=headers, json=payload).json()["detail"]
            == "wish_performance_player_scope_mismatch"
        )
        pp.performance_id = performances[0].id
        db_session.commit()
        assert (
            client.post("/admin/wishes", headers=headers, json=payload).json()["detail"]
            == "actor_role_capability_missing"
        )
    finally:
        app.dependency_overrides.clear()
