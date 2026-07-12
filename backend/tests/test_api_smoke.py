from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import LeaveRequest
from app.services.auth import create_access_token


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_dashboard_requires_auth():
    client = TestClient(app)
    response = client.get("/admin/dashboard")
    assert response.status_code == 401


def test_actor_schedule_requires_auth():
    client = TestClient(app)
    response = client.get("/actor/me/schedule")
    assert response.status_code == 401


def test_actor_can_submit_full_day_leave_request(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        token = create_access_token("actor@example.com", "actor")
        response = client.post(
            "/actor/me/leave-requests",
            headers={"Authorization": f"Bearer {token}"},
            json={"dates": ["2026-06-05"], "note": "提前请假"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "submitted", "dates": ["2026-06-05"]}
        stored = db_session.query(LeaveRequest).one()
        assert stored.leave_date.isoformat() == "2026-06-05"
        assert stored.note == "提前请假"
    finally:
        app.dependency_overrides.clear()
