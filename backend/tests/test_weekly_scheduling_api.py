from datetime import date, datetime, time
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from sqlalchemy.exc import IntegrityError

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    DesignationLifecycleEvent,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    LeaveRequest,
    Performance,
    Role,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    User,
    WeeklyBatch,
    WeeklyPublishOperation,
    Wish,
    PlayerProfile,
)
from app.models.enums import (
    BatchStatus,
    DesignationType,
    EntitlementEventType,
    EntitlementItemStatus,
    LeaveStatus,
    PerformanceStatus,
    PlayerStatus,
    UserRole,
)
from app.services.auth import create_access_token
from app.services.weekly_scheduling import _get_or_create_locked_batch


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_access_token("admin@example.com", "admin")
    return client, {"Authorization": f"Bearer {token}"}


def _seed_workspace(db_session):
    theater = Theater(name="西安幽州剧场")
    other = Theater(name="其他剧场")
    actors = [
        Actor(display_name="小展", max_consecutive_performances=3),
        Actor(display_name="小雨", max_consecutive_performances=3),
    ]
    db_session.add_all(
        [
            theater,
            other,
            *actors,
            User(email="admin@example.com", password_hash="x", role=UserRole.ADMIN),
        ]
    )
    db_session.flush()
    slots = [
        TheaterSlot(theater_id=theater.id, name="早场", start_time=time(12, 30), sort_order=0),
        TheaterSlot(theater_id=theater.id, name="晚场", start_time=time(19, 30), sort_order=1),
    ]
    roles = [Role(theater_id=theater.id, name="柳知雨"), Role(theater_id=theater.id, name="谢允昭")]
    other_role = Role(theater_id=other.id, name="柳知雨")
    db_session.add_all([*slots, *roles, other_role])
    db_session.flush()
    db_session.add_all(
        [
            ActorRoleCapability(actor_id=actors[0].id, role_id=roles[0].id),
            ActorRoleCapability(actor_id=actors[0].id, role_id=roles[1].id),
            ActorRoleCapability(actor_id=actors[1].id, role_id=roles[1].id),
            ActorRoleCapability(actor_id=actors[1].id, role_id=other_role.id),
        ]
    )
    performances = [
        Performance(
            theater_id=theater.id,
            theater_slot_id=slots[0].id,
            performance_date=date(2026, 12, 31),
            slot_name_snapshot="早场",
            start_time_snapshot=time(12, 30),
        ),
        Performance(
            theater_id=theater.id,
            theater_slot_id=slots[1].id,
            performance_date=date(2027, 1, 1),
            slot_name_snapshot="晚场",
            start_time_snapshot=time(19, 30),
        ),
    ]
    db_session.add_all(performances)
    db_session.commit()
    return theater, actors, roles, performances


def test_batch_unique_race_recovers_savepoint_winner_without_outer_rollback():
    winner = WeeklyBatch(id=44, theater_id=9, week_start=date(2026, 12, 28), version=3)
    db = MagicMock()
    db.scalar.side_effect = [None, winner]
    db.connection.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connection=SimpleNamespace(driver_connection=None),
    )
    nested = MagicMock()
    nested.__enter__.return_value = nested
    nested.__exit__.return_value = False
    db.begin_nested.return_value = nested
    db.flush.side_effect = IntegrityError("INSERT weekly_batches", {}, Exception("unique"))

    result = _get_or_create_locked_batch(db, 9, date(2026, 12, 28))

    assert result is winner
    assert db.scalar.call_count == 2
    assert db.begin_nested.call_count == 1
    db.rollback.assert_not_called()
    # The winner's version is the value persist_schedule subsequently compares;
    # a loser carrying expected_version=0 receives stable schedule_version_conflict(3).
    assert result.version == 3


def test_workspace_loads_cross_year_performances_and_rejects_non_monday(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    try:
        response = client.get(
            f"/admin/weekly-schedules/workspace?theater_id={theater.id}&week_start=2026-12-28",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["week_end"] == "2027-01-03"
        assert [item["id"] for item in body["performances"]] == [item.id for item in performances]
        assert [item["id"] for item in body["roles"]] == [item.id for item in roles]
        assert body["version"] == 0
        assert body["status"] == "uncreated"
        assert (
            client.get(
                f"/admin/weekly-schedules/workspace?theater_id={theater.id}&week_start=2026-12-29",
                headers=headers,
            ).status_code
            == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_active_predesignation_is_injected_as_locked_and_cannot_be_overwritten(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="玩家A",
        role_id=roles[0].id,
        actor_id=actors[0].id,
        performance_id=performances[0].id,
        target_performance_id=performances[0].id,
        submitted_at=datetime(2026, 12, 20, 10),
        lifecycle_status="predesignated",
    )
    db_session.add(designation)
    db_session.commit()
    client, headers = _client(db_session)
    try:
        workspace = client.get(
            f"/admin/weekly-schedules/workspace?theater_id={theater.id}&week_start=2026-12-28",
            headers=headers,
        )
        assert workspace.status_code == 200
        locked = next(
            row
            for row in workspace.json()["assignments"]
            if row["designation_id"] == designation.id
        )
        expected = {
            "performance_id": performances[0].id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "locked": True,
            "designation_type": "universal",
            "owner_player_name": "玩家A",
            "beneficiary_player_name": "玩家A",
        }
        assert {key: locked[key] for key in expected} == expected

        changed = {**locked, "actor_id": actors[1].id}
        rejected = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": [changed],
                "confirm_conflicts": True,
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "predesignation_locked"
        assert db_session.query(WeeklyBatch).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_recommend_reinjects_locked_predesignation_over_manual_payload(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="P",
        role_id=roles[1].id,
        actor_id=actors[0].id,
        performance_id=performances[1].id,
        target_performance_id=performances[1].id,
        submitted_at=datetime.utcnow(),
        lifecycle_status="predesignated",
    )
    db_session.add(designation)
    db_session.commit()
    client, headers = _client(db_session)
    try:
        response = client.post(
            "/admin/weekly-schedules/recommend",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "assignments": [
                    {
                        "performance_id": performances[1].id,
                        "role_id": roles[1].id,
                        "actor_id": actors[1].id,
                        "source": "manual",
                    }
                ],
            },
        )
        assert response.status_code == 200
        cell = next(
            row
            for row in response.json()["assignments"]
            if row["performance_id"] == performances[1].id and row["role_id"] == roles[1].id
        )
        assert cell["actor_id"] == actors[0].id and cell["locked"] is True
    finally:
        app.dependency_overrides.clear()


def test_publish_consumes_fulfilled_reserved_item_once_with_lifecycle_audit(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    player = PlayerProfile(display_name="P", normalized_name="p", status=PlayerStatus.ACTIVE)
    item_type = EntitlementItemType(
        code="universal", display_name="万能", priority=1, default_validity_months=12
    )
    db_session.add_all([player, item_type])
    db_session.flush()
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="P",
        role_id=roles[0].id,
        actor_id=actors[0].id,
        performance_id=performances[0].id,
        target_performance_id=performances[0].id,
        submitted_at=datetime.utcnow(),
        lifecycle_status="predesignated",
        owner_player_id=player.id,
    )
    db_session.add(designation)
    db_session.flush()
    item = EntitlementItem(
        serial_number="PUB-1",
        owner_id=player.id,
        item_type_id=item_type.id,
        source_month=date(2026, 1, 1),
        source_label="test",
        granted_at=datetime(2026, 1, 1),
        expires_at=datetime(2027, 12, 31),
        status=EntitlementItemStatus.RESERVED,
        current_designation_id=designation.id,
    )
    db_session.add(item)
    db_session.flush()
    designation.entitlement_item_id = item.id
    db_session.commit()
    client, headers = _client(db_session)
    assignments = [
        {
            "performance_id": performances[0].id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "source": "recommended",
        },
        {
            "performance_id": performances[0].id,
            "role_id": roles[1].id,
            "actor_id": actors[0].id,
            "source": "manual",
        },
        {
            "performance_id": performances[1].id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "source": "manual",
        },
        {
            "performance_id": performances[1].id,
            "role_id": roles[1].id,
            "actor_id": actors[1].id,
            "source": "manual",
        },
    ]
    try:
        response = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": assignments,
                "confirm_conflicts": True,
                "idempotency_key": "pub-one",
            },
        )
        assert response.status_code == 200
        db_session.refresh(item)
        db_session.refresh(designation)
        assert item.status == EntitlementItemStatus.CONSUMED
        assert designation.lifecycle_status == "fulfilled"
        assert db_session.query(EntitlementLedgerEntry).filter_by(item_id=item.id).count() == 1
        assert (
            db_session.query(DesignationLifecycleEvent)
            .filter_by(designation_id=designation.id, action="publish_fulfill")
            .count()
            == 1
        )
        replay = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": assignments,
                "confirm_conflicts": True,
                "idempotency_key": "pub-one",
            },
        )
        assert replay.status_code == 200 and replay.json() == response.json()
        assert db_session.query(EntitlementLedgerEntry).filter_by(item_id=item.id).count() == 1
        mismatch = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": [*assignments[:-1], {**assignments[-1], "source": "recommended"}],
                "confirm_conflicts": True,
                "idempotency_key": "pub-one",
            },
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "publish_idempotency_hash_conflict"
    finally:
        app.dependency_overrides.clear()


def test_recommend_prioritizes_confirmed_designation_without_overwriting_manual_assignment(
    db_session,
):
    theater, actors, roles, performances = _seed_workspace(db_session)
    batch = WeeklyBatch(
        theater_id=theater.id, week_start=date(2026, 12, 28), status=BatchStatus.DRAFT
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        Designation(
            designation_type=DesignationType.UNIVERSAL,
            player_name="玩家A",
            role_id=roles[1].id,
            actor_id=actors[0].id,
            target_performance_id=performances[1].id,
            submitted_at=datetime(2026, 12, 20, 10),
            weekly_batch_id=batch.id,
        )
    )
    db_session.commit()
    client, headers = _client(db_session)
    try:
        response = client.post(
            "/admin/weekly-schedules/recommend",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": batch.version,
                "assignments": [
                    {
                        "performance_id": performances[0].id,
                        "role_id": roles[0].id,
                        "actor_id": actors[0].id,
                        "source": "manual",
                    }
                ],
            },
        )
        assert response.status_code == 200
        assignments = response.json()["assignments"]
        assert assignments[0]["source"] == "manual"
        assert any(
            row["performance_id"] == performances[1].id
            and row["role_id"] == roles[1].id
            and row["actor_id"] == actors[0].id
            for row in assignments
        )
        assert response.json()["unsatisfied_designations"] == []
    finally:
        app.dependency_overrides.clear()


def test_recommend_applies_wish_only_to_its_performance_and_marks_reason(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    # Actor 0 can play role 0; make actor 1 eligible so the wish changes the tie only in performance 1.
    db_session.add(ActorRoleCapability(actor_id=actors[1].id, role_id=roles[0].id))
    db_session.add(
        Wish(
            player_name="Sunny",
            role_id=roles[0].id,
            actor_id=actors[1].id,
            performance_id=performances[1].id,
            performance_player_id=999,
            status="active",
        )
    )
    db_session.commit()
    client, headers = _client(db_session)
    try:
        response = client.post(
            "/admin/weekly-schedules/recommend",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "assignments": [],
            },
        )
        assert response.status_code == 200
        rows = response.json()["assignments"]
        assert (
            next(
                row
                for row in rows
                if row["performance_id"] == performances[0].id and row["role_id"] == roles[0].id
            )["actor_id"]
            == actors[0].id
        )
        assert (
            next(
                row
                for row in rows
                if row["performance_id"] == performances[1].id and row["role_id"] == roles[0].id
            )["actor_id"]
            == actors[1].id
        )
        assert any("wish" in reason for row in rows for reason in row["recommendation_reasons"])
    finally:
        app.dependency_overrides.clear()


def test_unmet_wish_has_reason_but_does_not_block_publish(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    db_session.add(
        Wish(
            player_name="P",
            role_id=roles[0].id,
            actor_id=actors[1].id,
            performance_id=performances[0].id,
            performance_player_id=999,
            status="active",
        )
    )
    db_session.commit()
    client, headers = _client(db_session)
    try:
        recommended = client.post(
            "/admin/weekly-schedules/recommend",
            headers=headers,
            json={"theater_id": theater.id, "week_start": "2026-12-28", "assignments": []},
        )
        assert recommended.status_code == 200
        assert (
            recommended.json()["unsatisfied_wishes"][0]["failure_reason"]
            == "hard_rules_or_higher_priority_assignment"
        )
        published = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": recommended.json()["assignments"],
                "confirm_conflicts": True,
            },
        )
        assert published.status_code == 200
        assert published.json()["status"] == "scheduled"
    finally:
        app.dependency_overrides.clear()


def test_legacy_batch_without_publish_operation_still_loads_saves_and_publishes(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    base = {
        "theater_id": theater.id,
        "week_start": "2026-12-28",
        "expected_version": 0,
        "assignments": [
            {
                "performance_id": performances[0].id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
                "source": "manual",
            }
        ],
    }
    try:
        recommended = client.post("/admin/weekly-schedules/recommend", headers=headers, json=base)
        assert recommended.status_code == 200
        rows = recommended.json()["assignments"]
        assert rows[0]["actor_id"] == actors[0].id
        assert rows[0]["source"] == "manual"
        assert len(rows) > 1

        conflicting = {
            **base,
            "assignments": [
                {
                    "performance_id": performances[0].id,
                    "role_id": roles[0].id,
                    "actor_id": actors[1].id,
                    "source": "manual",
                },
                {
                    "performance_id": performances[0].id,
                    "role_id": roles[1].id,
                    "actor_id": actors[0].id,
                    "source": "manual",
                },
                {
                    "performance_id": performances[1].id,
                    "role_id": roles[0].id,
                    "actor_id": actors[0].id,
                    "source": "manual",
                },
                {
                    "performance_id": performances[1].id,
                    "role_id": roles[1].id,
                    "actor_id": actors[1].id,
                    "source": "manual",
                },
            ],
        }
        rejected = client.put("/admin/weekly-schedules/draft", headers=headers, json=conflicting)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "conflicts_require_confirmation"
        assert db_session.query(WeeklyBatch).count() == 0

        saved = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={**conflicting, "confirm_conflicts": True},
        )
        assert saved.status_code == 200
        assert saved.json()["status"] == "ready"
        assert saved.json()["version"] == 1

        actor_email = "scheduled-actor@example.com"
        db_session.add(
            User(
                email=actor_email, password_hash="test", role=UserRole.ACTOR, actor_id=actors[1].id
            )
        )
        db_session.commit()
        actor_headers = {"Authorization": f"Bearer {create_access_token(actor_email, 'actor')}"}
        assert client.get("/actor/me/schedule", headers=actor_headers).json() == []

        published = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={**conflicting, "expected_version": 1, "confirm_conflicts": True},
        )
        assert published.status_code == 200
        assert published.json()["status"] == "scheduled"
        assert published.json()["version"] == 2
        batch = db_session.query(WeeklyBatch).one()
        assert batch.status == BatchStatus.SCHEDULED
        assert batch.assignments[0].conflict_codes == ["role_not_allowed"]
        actor_schedule = client.get("/actor/me/schedule", headers=actor_headers)
        assert actor_schedule.status_code == 200
        assert actor_schedule.json() == [
            {
                "date": "2026-12-31",
                "slot": "早场",
                "role": "柳知雨",
                "status": "draft",
            },
            {"date": "2027-01-01", "slot": "晚场", "role": "谢允昭", "status": "draft"},
        ]

        stale = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={**conflicting, "expected_version": 1, "confirm_conflicts": True},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "schedule_version_conflict"
        assert stale.json()["detail"]["current_version"] == 2
    finally:
        app.dependency_overrides.clear()


def test_publish_rejects_partially_assigned_performance_even_when_conflicts_are_confirmed(
    db_session,
):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    payload = {
        "theater_id": theater.id,
        "week_start": "2026-12-28",
        "expected_version": 0,
        "confirm_conflicts": True,
        "assignments": [
            {
                "performance_id": performances[0].id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
                "source": "manual",
            }
        ],
    }
    try:
        response = client.post("/admin/weekly-schedules/publish", headers=headers, json=payload)
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "incomplete_performances",
            "performances": [
                {
                    "performance_id": performances[0].id,
                    "missing_role_ids": [roles[1].id],
                },
                {
                    "performance_id": performances[1].id,
                    "missing_role_ids": [roles[0].id, roles[1].id],
                },
            ],
        }
        assert db_session.query(WeeklyBatch).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_publish_rejects_zero_assignments_for_every_active_performance(db_session):
    theater, _, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    try:
        response = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": [],
                "confirm_conflicts": True,
                "idempotency_key": "empty",
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "incomplete_performances",
            "performances": [
                {"performance_id": performance.id, "missing_role_ids": [role.id for role in roles]}
                for performance in performances
            ],
        }
        assert db_session.query(WeeklyBatch).count() == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "scenario,reason,destination",
    [
        ("leave", "actor_on_leave", EntitlementItemStatus.EXPIRED),
        ("cancelled", "performance_cancelled", EntitlementItemStatus.AVAILABLE),
    ],
)
def test_unmet_requires_exact_token_then_refunds_with_release_event(
    db_session, scenario, reason, destination
):
    theater, actors, roles, performances = _seed_workspace(db_session)
    player = PlayerProfile(
        display_name="Owner", normalized_name="owner", status=PlayerStatus.ACTIVE
    )
    item_type = EntitlementItemType(
        code="universal", display_name="万能", priority=1, default_validity_months=12
    )
    db_session.add_all([player, item_type])
    db_session.flush()
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="Legacy",
        role_id=roles[0].id,
        actor_id=actors[0].id,
        performance_id=performances[0].id,
        target_performance_id=performances[0].id,
        submitted_at=datetime.utcnow(),
        lifecycle_status="predesignated",
        owner_player_id=player.id,
    )
    db_session.add(designation)
    db_session.flush()
    item = EntitlementItem(
        serial_number=f"REFUND-{scenario}",
        owner_id=player.id,
        item_type_id=item_type.id,
        source_month=date(2026, 1, 1),
        source_label="test",
        granted_at=datetime(2026, 1, 1),
        expires_at=datetime(2026, 6, 1) if scenario == "leave" else datetime(2027, 6, 1),
        status=EntitlementItemStatus.RESERVED,
        current_designation_id=designation.id,
    )
    db_session.add(item)
    if scenario == "leave":
        db_session.add(
            LeaveRequest(
                actor_id=actors[0].id,
                leave_date=performances[0].performance_date,
                status=LeaveStatus.APPROVED,
            )
        )
    else:
        performances[0].status = PerformanceStatus.CANCELLED
    db_session.flush()
    designation.entitlement_item_id = item.id
    db_session.commit()
    assignments = (
        []
        if scenario == "cancelled"
        else [
            {
                "performance_id": performances[0].id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
                "source": "recommended",
            },
            {
                "performance_id": performances[0].id,
                "role_id": roles[1].id,
                "actor_id": actors[1].id,
                "source": "manual",
            },
        ]
    ) + [
        {
            "performance_id": performances[1].id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "source": "manual",
        },
        {
            "performance_id": performances[1].id,
            "role_id": roles[1].id,
            "actor_id": actors[1].id,
            "source": "manual",
        },
    ]
    client, headers = _client(db_session)
    base = {
        "theater_id": theater.id,
        "week_start": "2026-12-28",
        "expected_version": 0,
        "assignments": assignments,
        "confirm_conflicts": True,
        "idempotency_key": "leave-refund",
    }
    try:
        first = client.post("/admin/weekly-schedules/publish", headers=headers, json=base)
        assert first.status_code == 409
        detail = first.json()["detail"]
        assert detail["code"] == "unmet_designations_require_confirmation"
        expected = {
            "id": designation.id,
            "version": 1,
            "failure_reason": reason,
            "entitlement_item_id": item.id,
            "item_current_status": "reserved",
            "refund_target": "Owner",
            "refund_status": destination.value,
        }
        assert {key: detail["designations"][0][key] for key in expected} == expected
        wrong = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={**base, "confirmation_token": "wrong"},
        )
        assert (
            wrong.status_code == 409
            and wrong.json()["detail"]["code"] == "publish_confirmation_token_required"
        )
        final = client.post(
            "/admin/weekly-schedules/publish",
            headers=headers,
            json={**base, "confirmation_token": detail["confirmation_token"]},
        )
        assert final.status_code == 200
        db_session.refresh(item)
        db_session.refresh(designation)
        assert item.status == destination and designation.lifecycle_status == "unsatisfied"
        ledger = db_session.query(EntitlementLedgerEntry).filter_by(item_id=item.id).one()
        assert (
            ledger.event_type == EntitlementEventType.RELEASED and ledger.to_status == destination
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "failure_stage",
    ["assignments", "item_and_entitlement_ledger", "designation_event", "operation_snapshot"],
)
def test_publish_failure_checkpoint_rolls_back_every_domain(db_session, monkeypatch, failure_stage):
    import app.services.weekly_scheduling as service

    theater, actors, roles, performances = _seed_workspace(db_session)
    player = PlayerProfile(
        display_name="Rollback",
        normalized_name=f"rollback-{failure_stage}",
        status=PlayerStatus.ACTIVE,
    )
    typ = EntitlementItemType(
        code="universal", display_name="万能", priority=1, default_validity_months=12
    )
    db_session.add_all([player, typ])
    db_session.flush()
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="Rollback",
        role_id=roles[0].id,
        actor_id=actors[0].id,
        performance_id=performances[0].id,
        target_performance_id=performances[0].id,
        submitted_at=datetime.utcnow(),
        lifecycle_status="predesignated",
        owner_player_id=player.id,
    )
    db_session.add(designation)
    db_session.flush()
    item = EntitlementItem(
        serial_number=f"ROLL-{failure_stage}",
        owner_id=player.id,
        item_type_id=typ.id,
        source_month=date(2026, 1, 1),
        source_label="test",
        granted_at=datetime(2026, 1, 1),
        expires_at=datetime(2027, 1, 1),
        status=EntitlementItemStatus.RESERVED,
        current_designation_id=designation.id,
    )
    db_session.add(item)
    db_session.flush()
    designation.entitlement_item_id = item.id
    db_session.commit()
    assignments = [
        {"performance_id": p.id, "role_id": r.id, "actor_id": actors[0].id, "source": "manual"}
        for p in performances
        for r in roles
    ]

    def fail(stage):
        if stage == failure_stage:
            raise RuntimeError(f"injected:{stage}")

    monkeypatch.setattr(service, "_publish_checkpoint", fail)
    client, headers = _client(db_session)
    try:
        with pytest.raises(RuntimeError, match=failure_stage):
            client.post(
                "/admin/weekly-schedules/publish",
                headers=headers,
                json={
                    "theater_id": theater.id,
                    "week_start": "2026-12-28",
                    "expected_version": 0,
                    "assignments": assignments,
                    "confirm_conflicts": True,
                    "idempotency_key": f"rollback-{failure_stage}",
                },
            )
        db_session.expire_all()
        assert db_session.query(WeeklyBatch).count() == 0
        assert db_session.query(ScheduleAssignment).count() == 0
        assert db_session.query(WeeklyPublishOperation).count() == 0
        assert db_session.query(EntitlementLedgerEntry).count() == 0
        assert db_session.query(DesignationLifecycleEvent).count() == 0
        assert db_session.get(EntitlementItem, item.id).status == EntitlementItemStatus.RESERVED
        assert db_session.get(Designation, designation.id).lifecycle_status == "predesignated"
    finally:
        app.dependency_overrides.clear()


def test_validate_counts_assignments_from_adjacent_draft_batch_for_consecutive_warning(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    actors[0].max_consecutive_performances = 2
    previous_performance = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 12, 27),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    current_performance = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 12, 28),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    db_session.add_all([previous_performance, current_performance])
    db_session.flush()
    previous_batch = WeeklyBatch(
        theater_id=theater.id,
        week_start=date(2026, 12, 21),
        status=BatchStatus.READY,
    )
    db_session.add(previous_batch)
    db_session.flush()
    db_session.add(
        ScheduleAssignment(
            weekly_batch_id=previous_batch.id,
            performance_id=previous_performance.id,
            role_id=roles[0].id,
            actor_id=actors[0].id,
            source="manual",
        )
    )
    db_session.commit()
    client, headers = _client(db_session)

    try:
        response = client.post(
            "/admin/weekly-schedules/validate",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": [
                    {
                        "performance_id": current_performance.id,
                        "role_id": roles[0].id,
                        "actor_id": actors[0].id,
                        "source": "manual",
                    }
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["warnings"] == [
            {
                "code": "consecutive_limit_reached",
                "message": "已达到演员个人最大连场数",
                "performance_id": current_performance.id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
            }
        ]
    finally:
        app.dependency_overrides.clear()


def test_context_validation_detects_unsaved_cross_week_warning_and_conflict(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    actors[0].max_consecutive_performances = 2
    dates = [date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)]
    context_performances = [
        Performance(
            theater_id=theater.id,
            theater_slot_id=performances[0].theater_slot_id,
            performance_date=performance_date,
            slot_name_snapshot="早场",
            start_time_snapshot=time(12, 30),
        )
        for performance_date in dates
    ]
    db_session.add_all(context_performances)
    db_session.commit()
    client, headers = _client(db_session)

    def assignment(performance):
        return {
            "performance_id": performance.id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "source": "manual",
        }

    try:
        response = client.post(
            "/admin/weekly-schedules/validate-context",
            headers=headers,
            json={
                "theater_id": theater.id,
                "weeks": [
                    {
                        "week_start": "2026-07-27",
                        "assignments": [assignment(context_performances[0])],
                    },
                    {
                        "week_start": "2026-08-03",
                        "assignments": [
                            assignment(context_performances[1]),
                            assignment(context_performances[2]),
                        ],
                    },
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert any(
            item["code"] == "consecutive_limit_reached"
            and item["performance_id"] == context_performances[1].id
            for item in body["warnings"]
        )
        assert any(
            item["code"] == "consecutive_limit_exceeded"
            and item["performance_id"] == context_performances[2].id
            for item in body["conflicts"]
        )
    finally:
        app.dependency_overrides.clear()


def test_context_validation_marks_only_the_third_and_fourth_consecutive_assignments(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    slot_ids = [performances[0].theater_slot_id, performances[1].theater_slot_id]
    consecutive_performances = [
        Performance(
            theater_id=theater.id,
            theater_slot_id=slot_ids[index % 2],
            performance_date=date(2026, 8, 3 + index // 2),
            slot_name_snapshot=f"第{index + 1}场",
            start_time_snapshot=time(12 if index % 2 == 0 else 19, 30),
        )
        for index in range(4)
    ]
    db_session.add_all(consecutive_performances)
    db_session.commit()
    client, headers = _client(db_session)

    try:
        response = client.post(
            "/admin/weekly-schedules/validate-context",
            headers=headers,
            json={
                "theater_id": theater.id,
                "weeks": [
                    {
                        "week_start": "2026-08-03",
                        "assignments": [
                            {
                                "performance_id": performance.id,
                                "role_id": roles[0].id,
                                "actor_id": actors[0].id,
                                "source": "manual",
                            }
                            for performance in consecutive_performances
                        ],
                    }
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert [(item["code"], item["performance_id"]) for item in body["warnings"]] == [
            ("consecutive_limit_reached", consecutive_performances[2].id),
        ]
        assert [(item["code"], item["performance_id"]) for item in body["conflicts"]] == [
            ("consecutive_limit_exceeded", consecutive_performances[3].id),
        ]
    finally:
        app.dependency_overrides.clear()


def test_context_validation_replaces_saved_assignments_for_supplied_weeks(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    actors[0].max_consecutive_performances = 2
    sunday = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 8, 2),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    monday = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 8, 3),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    db_session.add_all([sunday, monday])
    db_session.flush()
    batch = WeeklyBatch(
        theater_id=theater.id, week_start=date(2026, 7, 27), status=BatchStatus.READY
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        ScheduleAssignment(
            weekly_batch_id=batch.id,
            performance_id=sunday.id,
            role_id=roles[0].id,
            actor_id=actors[0].id,
            source="manual",
        )
    )
    db_session.commit()
    client, headers = _client(db_session)

    try:
        response = client.post(
            "/admin/weekly-schedules/validate-context",
            headers=headers,
            json={
                "theater_id": theater.id,
                "weeks": [
                    {"week_start": "2026-07-27", "assignments": []},
                    {
                        "week_start": "2026-08-03",
                        "assignments": [
                            {
                                "performance_id": monday.id,
                                "role_id": roles[0].id,
                                "actor_id": actors[0].id,
                                "source": "manual",
                            }
                        ],
                    },
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["warnings"] == []
        assert response.json()["conflicts"] == []
    finally:
        app.dependency_overrides.clear()


def test_recommend_uses_unsaved_adjacent_week_context(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    actors[0].max_consecutive_performances = 1
    db_session.add(ActorRoleCapability(actor_id=actors[1].id, role_id=roles[0].id))
    sunday = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 8, 2),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    monday = Performance(
        theater_id=theater.id,
        theater_slot_id=performances[0].theater_slot_id,
        performance_date=date(2026, 8, 3),
        slot_name_snapshot="早场",
        start_time_snapshot=time(12, 30),
    )
    db_session.add_all([sunday, monday])
    db_session.commit()
    client, headers = _client(db_session)

    try:
        response = client.post(
            "/admin/weekly-schedules/recommend",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-08-03",
                "expected_version": 0,
                "assignments": [],
                "context_weeks": [
                    {
                        "week_start": "2026-07-27",
                        "assignments": [
                            {
                                "performance_id": sunday.id,
                                "role_id": roles[0].id,
                                "actor_id": actors[0].id,
                                "source": "manual",
                            }
                        ],
                    }
                ],
            },
        )

        assert response.status_code == 200
        monday_role = next(
            row
            for row in response.json()["assignments"]
            if row["performance_id"] == monday.id and row["role_id"] == roles[0].id
        )
        assert monday_role["actor_id"] == actors[1].id
    finally:
        app.dependency_overrides.clear()
