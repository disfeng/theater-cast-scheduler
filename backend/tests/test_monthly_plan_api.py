from datetime import date
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.schemas.admin import ActorCreate, TheaterCreate
from app.services.admin_data import create_actor, create_theater
from app.services.auth import create_access_token
from app.models.entities import Designation, Performance, Role, ScheduleAssignment
from app.models.enums import DesignationType
from app.models.enums import PerformanceStatus


def test_generate_monthly_plan_persists_performances_and_skips_closed_dates(db_session):
    theater = create_theater(
        db_session,
        TheaterCreate(
            name="西幽剧场",
            default_weekly_template={
                "monday": ["early", "late"],
                "tuesday": ["late"],
                "wednesday": ["late"],
                "thursday": ["late"],
                "friday": ["early", "late"],
                "saturday": ["early", "late"],
                "sunday": ["early", "late"],
            },
        ),
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        token = create_access_token("admin@example.com", "admin")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/admin/monthly-plan/generate",
            headers=headers,
            json={
                "theater_id": theater.id,
                "year": 2026,
                "month": 6,
                "closed_dates": ["2026-06-02"],
            },
        )

        assert response.status_code == 200
        dates = {(item["performance_date"], item["slot"]) for item in response.json()}
        assert ("2026-06-01", "early") in dates
        assert ("2026-06-01", "late") in dates
        assert ("2026-06-02", "late") not in dates
        list_response = client.get(
            f"/admin/performances?theater_id={theater.id}&year=2026&month=6",
            headers=headers,
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == len(response.json())
    finally:
        app.dependency_overrides.clear()


def _admin_headers():
    token = create_access_token("admin@example.com", "admin")
    return {"Authorization": f"Bearer {token}"}


def test_monthly_regeneration_rejects_non_draft_performances(db_session):
    theater = create_theater(
        db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]})
    )
    performance = Performance(
        theater_id=theater.id,
        performance_date=date(2026, 6, 1),
        slot="early",
        status=PerformanceStatus.PUBLISHED,
    )
    db_session.add(performance)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id).status == PerformanceStatus.PUBLISHED
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_rejects_referenced_draft(db_session):
    theater = create_theater(
        db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]})
    )
    role = Role(name="长离")
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    performance = Performance(
        theater_id=theater.id, performance_date=date(2026, 6, 1), slot="early"
    )
    db_session.add_all([role, performance])
    db_session.flush()
    db_session.add(
        ScheduleAssignment(performance_id=performance.id, role_id=role.id, actor_id=actor.id)
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_list_performances_filters_by_theater(db_session):
    first = create_theater(
        db_session,
        TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}),
    )
    second = create_theater(
        db_session,
        TheaterCreate(name="东幽剧场", default_weekly_template={"monday": ["late"]}),
    )
    db_session.add_all(
        [
            Performance(
                theater_id=first.id,
                performance_date=date(2026, 6, 1),
                slot="early",
            ),
            Performance(
                theater_id=second.id,
                performance_date=date(2026, 6, 1),
                slot="late",
            ),
        ]
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get(
            f"/admin/performances?theater_id={first.id}&year=2026&month=6",
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        assert [item["theater_id"] for item in response.json()] == [first.id]
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_replaces_unreferenced_drafts(db_session):
    theater = create_theater(
        db_session,
        TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["late"]}),
    )
    old = Performance(
        theater_id=theater.id,
        performance_date=date(2026, 6, 1),
        slot="early",
    )
    db_session.add(old)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 200
        assert {item["slot"] for item in response.json()} == {"late"}
        stored = db_session.query(Performance).filter_by(theater_id=theater.id).all()
        assert {item.slot for item in stored} == {"late"}
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_rejects_designation_referenced_draft(db_session):
    theater = create_theater(
        db_session,
        TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}),
    )
    role = Role(name="长离")
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    performance = Performance(
        theater_id=theater.id,
        performance_date=date(2026, 6, 1),
        slot="early",
    )
    db_session.add_all([role, performance])
    db_session.flush()
    db_session.add(
        Designation(
            designation_type=DesignationType.UNIVERSAL,
            player_name="玩家甲",
            role_id=role.id,
            actor_id=actor.id,
            target_performance_id=performance.id,
            submitted_at=date(2026, 5, 1),
        )
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/admin/monthly-plan/generate",
            headers=_admin_headers(),
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []},
        )
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id) is not None
    finally:
        app.dependency_overrides.clear()
