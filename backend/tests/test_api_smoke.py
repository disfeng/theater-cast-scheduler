from fastapi.testclient import TestClient

from app.main import app


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
