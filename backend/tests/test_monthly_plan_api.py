from datetime import date
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.schemas.admin import ActorCreate, TheaterCreate
from app.services.admin_data import create_actor, create_theater
from app.services.auth import create_access_token
from app.models.entities import Performance, Role, ScheduleAssignment
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
        list_response = client.get("/admin/performances?year=2026&month=6", headers=headers)
        assert list_response.status_code == 200
        assert len(list_response.json()) == len(response.json())
    finally:
        app.dependency_overrides.clear()


def _admin_headers():
    token = create_access_token("admin@example.com", "admin")
    return {"Authorization": f"Bearer {token}"}


def test_monthly_regeneration_rejects_non_draft_performances(db_session):
    theater = create_theater(db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}))
    performance = Performance(theater_id=theater.id, performance_date=date(2026, 6, 1), slot="early", status=PerformanceStatus.PUBLISHED)
    db_session.add(performance)
    db_session.commit()
    
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post("/admin/monthly-plan/generate", headers=_admin_headers(), json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []})
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id).status == PerformanceStatus.PUBLISHED
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_rejects_referenced_draft(db_session):
    theater = create_theater(db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}))
    role = Role(name="长离")
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    performance = Performance(theater_id=theater.id, performance_date=date(2026, 6, 1), slot="early")
    db_session.add_all([role, performance])
    db_session.flush()
    db_session.add(ScheduleAssignment(performance_id=performance.id, role_id=role.id, actor_id=actor.id))
    db_session.commit()
    
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post("/admin/monthly-plan/generate", headers=_admin_headers(), json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []})
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id) is not None
    finally:
        app.dependency_overrides.clear()
