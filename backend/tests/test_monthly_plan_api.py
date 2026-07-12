from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.schemas.admin import TheaterCreate
from app.services.admin_data import create_theater
from app.services.auth import create_access_token


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
