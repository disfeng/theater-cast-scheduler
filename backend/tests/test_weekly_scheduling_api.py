from datetime import date, datetime, time

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    Performance,
    Role,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    User,
    WeeklyBatch,
)
from app.models.enums import BatchStatus, DesignationType, UserRole
from app.services.auth import create_access_token


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
    actors = [Actor(display_name="小展", max_consecutive_performances=3), Actor(display_name="小雨", max_consecutive_performances=3)]
    db_session.add_all([theater, other, *actors])
    db_session.flush()
    slots = [
        TheaterSlot(theater_id=theater.id, name="早场", start_time=time(12, 30), sort_order=0),
        TheaterSlot(theater_id=theater.id, name="晚场", start_time=time(19, 30), sort_order=1),
    ]
    roles = [Role(theater_id=theater.id, name="柳知雨"), Role(theater_id=theater.id, name="谢允昭")]
    other_role = Role(theater_id=other.id, name="柳知雨")
    db_session.add_all([*slots, *roles, other_role])
    db_session.flush()
    db_session.add_all([
        ActorRoleCapability(actor_id=actors[0].id, role_id=roles[0].id),
        ActorRoleCapability(actor_id=actors[0].id, role_id=roles[1].id),
        ActorRoleCapability(actor_id=actors[1].id, role_id=roles[1].id),
        ActorRoleCapability(actor_id=actors[1].id, role_id=other_role.id),
    ])
    performances = [
        Performance(theater_id=theater.id, theater_slot_id=slots[0].id, performance_date=date(2026, 12, 31), slot_name_snapshot="早场", start_time_snapshot=time(12, 30)),
        Performance(theater_id=theater.id, theater_slot_id=slots[1].id, performance_date=date(2027, 1, 1), slot_name_snapshot="晚场", start_time_snapshot=time(19, 30)),
    ]
    db_session.add_all(performances)
    db_session.commit()
    return theater, actors, roles, performances


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
        assert client.get(
            f"/admin/weekly-schedules/workspace?theater_id={theater.id}&week_start=2026-12-29",
            headers=headers,
        ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_recommend_prioritizes_confirmed_designation_without_overwriting_manual_assignment(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 12, 28), status=BatchStatus.DRAFT)
    db_session.add(batch)
    db_session.flush()
    db_session.add(Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="玩家A",
        role_id=roles[1].id,
        actor_id=actors[0].id,
        target_performance_id=performances[1].id,
        submitted_at=datetime(2026, 12, 20, 10),
        weekly_batch_id=batch.id,
    ))
    db_session.commit()
    client, headers = _client(db_session)
    try:
        response = client.post("/admin/weekly-schedules/recommend", headers=headers, json={
            "theater_id": theater.id,
            "week_start": "2026-12-28",
            "expected_version": batch.version,
            "assignments": [{
                "performance_id": performances[0].id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
                "source": "manual",
            }],
        })
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


def test_recommend_preserves_manual_then_conflict_confirmation_saves_and_publishes(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    base = {
        "theater_id": theater.id,
        "week_start": "2026-12-28",
        "expected_version": 0,
        "assignments": [{"performance_id": performances[0].id, "role_id": roles[0].id, "actor_id": actors[0].id, "source": "manual"}],
    }
    try:
        recommended = client.post("/admin/weekly-schedules/recommend", headers=headers, json=base)
        assert recommended.status_code == 200
        rows = recommended.json()["assignments"]
        assert rows[0]["actor_id"] == actors[0].id
        assert rows[0]["source"] == "manual"
        assert len(rows) > 1

        conflicting = {**base, "assignments": [
            {"performance_id": performances[0].id, "role_id": roles[0].id, "actor_id": actors[1].id, "source": "manual"},
            {"performance_id": performances[0].id, "role_id": roles[1].id, "actor_id": actors[0].id, "source": "manual"},
        ]}
        rejected = client.put("/admin/weekly-schedules/draft", headers=headers, json=conflicting)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "conflicts_require_confirmation"
        assert db_session.query(WeeklyBatch).count() == 0

        saved = client.put("/admin/weekly-schedules/draft", headers=headers, json={**conflicting, "confirm_conflicts": True})
        assert saved.status_code == 200
        assert saved.json()["status"] == "ready"
        assert saved.json()["version"] == 1

        actor_email = "scheduled-actor@example.com"
        db_session.add(User(email=actor_email, password_hash="test", role=UserRole.ACTOR, actor_id=actors[1].id))
        db_session.commit()
        actor_headers = {"Authorization": f"Bearer {create_access_token(actor_email, 'actor')}"}
        assert client.get("/actor/me/schedule", headers=actor_headers).json() == []

        published = client.post("/admin/weekly-schedules/publish", headers=headers, json={**conflicting, "expected_version": 1, "confirm_conflicts": True})
        assert published.status_code == 200
        assert published.json()["status"] == "scheduled"
        assert published.json()["version"] == 2
        batch = db_session.query(WeeklyBatch).one()
        assert batch.status == BatchStatus.SCHEDULED
        assert batch.assignments[0].conflict_codes == ["role_not_allowed"]
        actor_schedule = client.get("/actor/me/schedule", headers=actor_headers)
        assert actor_schedule.status_code == 200
        assert actor_schedule.json() == [{
            "date": "2026-12-31",
            "slot": "早场",
            "role": "柳知雨",
            "status": "draft",
        }]

        stale = client.put("/admin/weekly-schedules/draft", headers=headers, json={**conflicting, "expected_version": 1, "confirm_conflicts": True})
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "schedule_version_conflict"
    finally:
        app.dependency_overrides.clear()


def test_publish_rejects_partially_assigned_performance_even_when_conflicts_are_confirmed(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    payload = {
        "theater_id": theater.id,
        "week_start": "2026-12-28",
        "expected_version": 0,
        "confirm_conflicts": True,
        "assignments": [{
            "performance_id": performances[0].id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
            "source": "manual",
        }],
    }
    try:
        response = client.post("/admin/weekly-schedules/publish", headers=headers, json=payload)
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "incomplete_performances",
            "performances": [{
                "performance_id": performances[0].id,
                "missing_role_ids": [roles[1].id],
            }],
        }
        assert db_session.query(WeeklyBatch).count() == 0
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
    db_session.add(ScheduleAssignment(
        weekly_batch_id=previous_batch.id,
        performance_id=previous_performance.id,
        role_id=roles[0].id,
        actor_id=actors[0].id,
        source="manual",
    ))
    db_session.commit()
    client, headers = _client(db_session)

    try:
        response = client.post("/admin/weekly-schedules/validate", headers=headers, json={
            "theater_id": theater.id,
            "week_start": "2026-12-28",
            "expected_version": 0,
            "assignments": [{
                "performance_id": current_performance.id,
                "role_id": roles[0].id,
                "actor_id": actors[0].id,
                "source": "manual",
            }],
        })

        assert response.status_code == 200
        assert response.json()["warnings"] == [{
            "code": "consecutive_limit_reached",
            "message": "已达到演员个人最大连场数",
            "performance_id": current_performance.id,
            "role_id": roles[0].id,
            "actor_id": actors[0].id,
        }]
    finally:
        app.dependency_overrides.clear()
