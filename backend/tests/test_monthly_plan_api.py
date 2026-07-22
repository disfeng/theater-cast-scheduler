from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Performance,
    Role,
    ScheduleAssignment,
    TheaterSlot,
    TheaterWeeklyTemplateEntry,
)
from app.models.enums import PerformanceStatus
from app.schemas.admin import ActorCreate, TheaterCreate
from app.services.admin_data import create_actor, create_theater
from auth_helpers import persisted_admin_headers_from_override
from app.services.monthly_plan import MonthlyPlanConflict, replace_monthly_plan


def _admin_headers():
    return persisted_admin_headers_from_override()


def _configured_theater(db_session, name="西幽剧场", slot_names=("午场", "晚场")):
    theater = create_theater(db_session, TheaterCreate(name=name))
    slots = []
    for index, slot_name in enumerate(slot_names):
        slot = TheaterSlot(
            theater_id=theater.id,
            name=slot_name,
            start_time=time(14 + index * 5),
            sort_order=index,
        )
        db_session.add(slot)
        db_session.flush()
        slots.append(slot)
    for slot in slots:
        db_session.add(
            TheaterWeeklyTemplateEntry(
                theater_id=theater.id,
                weekday="monday",
                theater_slot_id=slot.id,
            )
        )
    db_session.commit()
    return theater, slots


def _performance(
    theater_id, slot, performance_date=date(2026, 6, 1), status=PerformanceStatus.DRAFT
):
    return Performance(
        theater_id=theater_id,
        theater_slot_id=slot.id,
        performance_date=performance_date,
        slot_name_snapshot=slot.name,
        start_time_snapshot=slot.start_time,
        status=status,
    )


def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_generate_monthly_plan_persists_snapshots_and_skips_closed_dates(db_session):
    theater, slots = _configured_theater(db_session)
    client = _client(db_session)
    try:
        response = client.post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 200
        june_first = [item for item in response.json() if item["performance_date"] == "2026-06-01"]
        assert [item["slot_name_snapshot"] for item in june_first] == ["午场", "晚场"]
        assert [item["theater_slot_id"] for item in june_first] == [slot.id for slot in slots]

        closed = client.post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={
                "theater_id": theater.id,
                "year": 2026,
                "month": 6,
                "closed_dates": ["2026-06-01"],
            },
        )
        assert closed.status_code == 200
        assert all(item["performance_date"] != "2026-06-01" for item in closed.json())
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_rejects_non_draft_or_referenced_performances(db_session):
    theater, (slot, _) = _configured_theater(db_session)
    published = _performance(theater.id, slot, status=PerformanceStatus.PUBLISHED)
    db_session.add(published)
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()

    published.status = PerformanceStatus.DRAFT
    role = Role(theater_id=theater.id, name="长离")
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    db_session.add(role)
    db_session.flush()
    from app.models.entities import WeeklyBatch

    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 7, 6))
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        ScheduleAssignment(
            weekly_batch_id=batch.id,
            performance_id=published.id,
            role_id=role.id,
            actor_id=actor.id,
        )
    )
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_list_performances_filters_by_theater(db_session):
    first, (first_slot,) = _configured_theater(db_session, "西幽剧场", ("午场",))
    second, (second_slot,) = _configured_theater(db_session, "东幽剧场", ("晚场",))
    db_session.add_all([_performance(first.id, first_slot), _performance(second.id, second_slot)])
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.get(
            f"/admin/performances?theater_id={first.id}&year=2026&month=6",
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        assert [item["theater_id"] for item in response.json()] == [first.id]
    finally:
        app.dependency_overrides.clear()


def test_create_update_duplicate_and_delete_performance(db_session):
    theater, (slot,) = _configured_theater(db_session, slot_names=("午场",))
    client = _client(db_session)
    payload = {
        "theater_id": theater.id,
        "performance_date": "2026-06-15",
        "theater_slot_id": slot.id,
    }
    try:
        created = client.post("/admin/performances", headers=_admin_headers(), json=payload)
        assert created.status_code == 200
        data = created.json()
        assert data["slot_name_snapshot"] == "午场"
        assert data["start_time_snapshot"] == "14:00:00"

        duplicate = client.post("/admin/performances", headers=_admin_headers(), json=payload)
        assert duplicate.status_code == 409

        updated = client.patch(
            f"/admin/performances/{data['id']}",
            headers=_admin_headers(),
            json={"performance_date": "2026-06-16"},
        )
        assert updated.status_code == 200
        assert updated.json()["performance_date"] == "2026-06-16"

        deleted = client.delete(f"/admin/performances/{data['id']}", headers=_admin_headers())
        assert deleted.status_code == 200
        assert db_session.get(Performance, data["id"]) is None
    finally:
        app.dependency_overrides.clear()


def test_replace_monthly_plan_preserves_existing_and_diffs_slots(db_session):
    theater, (morning, evening) = _configured_theater(db_session, slot_names=("早场", "晚场"))
    existing = _performance(theater.id, morning, date(2026, 8, 3))
    removed = _performance(theater.id, evening, date(2026, 8, 4))
    db_session.add_all([existing, removed])
    db_session.commit()
    existing_id = existing.id
    removed_id = removed.id

    result = replace_monthly_plan(
        db_session,
        theater.id,
        2026,
        8,
        {date(2026, 8, 3): [morning.id, evening.id], date(2026, 8, 4): []},
    )

    assert db_session.get(Performance, existing_id) is not None
    assert db_session.get(Performance, removed_id) is None
    assert {(item.performance_date, item.theater_slot_id) for item in result} == {
        (date(2026, 8, 3), morning.id),
        (date(2026, 8, 3), evening.id),
    }


def test_replace_monthly_plan_rejects_invalid_date_and_cross_theater_slot(db_session):
    theater, (slot,) = _configured_theater(db_session, "西幽剧场", ("早场",))
    _, (other_slot,) = _configured_theater(db_session, "东幽剧场", ("早场",))

    with pytest.raises(ValueError, match="performance_date_outside_month"):
        replace_monthly_plan(db_session, theater.id, 2026, 8, {date(2026, 9, 1): [slot.id]})
    with pytest.raises(ValueError, match="invalid_theater_slot"):
        replace_monthly_plan(db_session, theater.id, 2026, 8, {date(2026, 8, 1): [other_slot.id]})


def test_replace_monthly_plan_conflict_is_atomic(db_session):
    theater, (morning, evening) = _configured_theater(db_session, slot_names=("早场", "晚场"))
    existing = _performance(theater.id, morning, date(2026, 8, 3), PerformanceStatus.PUBLISHED)
    db_session.add(existing)
    db_session.commit()

    with pytest.raises(MonthlyPlanConflict, match="monthly_plan_has_non_draft_performances"):
        replace_monthly_plan(
            db_session,
            theater.id,
            2026,
            8,
            {date(2026, 8, 4): [evening.id]},
        )

    assert db_session.get(Performance, existing.id) is not None
    assert (
        db_session.scalar(
            select(Performance).where(
                Performance.performance_date == date(2026, 8, 4),
                Performance.theater_slot_id == evening.id,
            )
        )
        is None
    )


def test_replace_monthly_plan_endpoint_saves_calendar(db_session):
    theater, (morning, evening) = _configured_theater(db_session, slot_names=("早场", "晚场"))
    client = _client(db_session)
    try:
        response = client.put(
            "/admin/monthly-plan",
            headers=_admin_headers(),
            json={
                "theater_id": theater.id,
                "year": 2026,
                "month": 8,
                "days": [
                    {"performance_date": "2026-08-03", "theater_slot_ids": [morning.id]},
                    {"performance_date": "2026-08-04", "theater_slot_ids": [evening.id]},
                ],
            },
        )
        assert response.status_code == 200
        assert {
            (item["performance_date"], item["slot_name_snapshot"]) for item in response.json()
        } == {
            ("2026-08-03", "早场"),
            ("2026-08-04", "晚场"),
        }
    finally:
        app.dependency_overrides.clear()


def test_replace_monthly_plan_endpoint_rejects_duplicate_dates(db_session):
    theater, (morning,) = _configured_theater(db_session, slot_names=("早场",))
    client = _client(db_session)
    try:
        response = client.put(
            "/admin/monthly-plan",
            headers=_admin_headers(),
            json={
                "theater_id": theater.id,
                "year": 2026,
                "month": 8,
                "days": [
                    {"performance_date": "2026-08-03", "theater_slot_ids": [morning.id]},
                    {"performance_date": "2026-08-03", "theater_slot_ids": []},
                ],
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
