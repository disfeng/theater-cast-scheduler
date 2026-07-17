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


def test_preview_rejects_new_unscoped_wish_and_scoped_wish_stays_on_target_performance():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('admin@example.com', 'admin')}"}
    base = {
        "performances": [
            {"id": 1, "date": "2026-06-05", "slot": "early"},
            {"id": 2, "date": "2026-06-06", "slot": "early"},
        ],
        "role_ids": [10],
        "actor_ids": [1, 2],
        "actor_role_ids": {"1": [10], "2": [10]},
        "max_consecutive": {"1": 3, "2": 3},
        "approved_leave_dates": {},
        "low_rating_caps": {},
        "monthly_counts": {"1": 1, "2": 0},
        "designations": [],
        "suspended_actor_ids": [],
    }
    rejected = client.post(
        "/scheduling/preview",
        headers=headers,
        json={**base, "wishes": [{"player_name": "P", "role_id": 10, "actor_id": 1}]},
    )
    assert rejected.status_code == 422
    accepted = client.post(
        "/scheduling/preview",
        headers=headers,
        json={
            **base,
            "wishes": [
                {
                    "player_name": "P",
                    "role_id": 10,
                    "actor_id": 1,
                    "performance_id": 2,
                    "performance_player_id": 9,
                }
            ],
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["assignments"] == [
        {"performance_id": 1, "role_id": 10, "actor_id": 2},
        {"performance_id": 2, "role_id": 10, "actor_id": 1},
    ]
