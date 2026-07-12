from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import create_access_token


def test_scheduling_preview_returns_assignments():
    client = TestClient(app)
    token = create_access_token("admin@example.com", "admin")
    response = client.post(
        "/scheduling/preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "performances": [{"id": 1, "date": "2026-06-05", "slot": "early"}],
            "role_ids": [10],
            "actor_ids": [1],
            "actor_role_ids": {"1": [10]},
            "max_consecutive": {"1": 3},
            "approved_leave_dates": {},
            "low_rating_caps": {},
            "monthly_counts": {},
            "designations": [],
            "wishes": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["assignments"] == [{"performance_id": 1, "role_id": 10, "actor_id": 1}]
