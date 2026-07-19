import base64

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.auth import create_access_token


def _admin_headers() -> dict[str, str]:
    token = create_access_token("admin@example.com", "admin")
    return {"Authorization": f"Bearer {token}"}


def _override_db(db_session):
    def override():
        yield db_session

    return override


def test_admin_creates_phone_actor_and_receives_one_time_pdf(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        theater = client.post(
            "/admin/theaters", headers=_admin_headers(), json={"name": "西安幽州剧场"}
        ).json()
        response = client.post(
            "/admin/actors",
            headers=_admin_headers(),
            json={
                "display_name": "小A",
                "phone_number": "138 0013 8000",
                "entry_theater_id": theater["id"],
                "theater_ids": [theater["id"]],
                "max_consecutive_performances": 3,
                "rating_level": "normal",
                "low_rating_monthly_cap": None,
                "notes": None,
            },
        )

        assert response.status_code == 200
        delivery = response.json()["credential_delivery"]
        assert response.json()["actor"]["phone_number"] == "13800138000"
        assert delivery["username"] == "13800138000"
        assert delivery["filename"] == "西安幽州剧场-小A.pdf"
        assert base64.b64decode(delivery["pdf_base64"]).startswith(b"%PDF")
        listed = client.get("/admin/actors", headers=_admin_headers()).json()[0]
        assert "initial_password" not in listed
        assert "credential_delivery" not in listed
    finally:
        app.dependency_overrides.clear()


def test_actor_phone_login_requires_password_change_before_business_routes(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        theater = client.post(
            "/admin/theaters", headers=_admin_headers(), json={"name": "西安幽州剧场"}
        ).json()
        created = client.post(
            "/admin/actors",
            headers=_admin_headers(),
            json={
                "display_name": "小A",
                "phone_number": "13800138000",
                "entry_theater_id": theater["id"],
                "theater_ids": [theater["id"]],
            },
        ).json()
        login = client.post(
            "/auth/login",
            json={
                "identifier": created["credential_delivery"]["username"],
                "password": created["credential_delivery"]["initial_password"],
            },
        )

        assert login.status_code == 200
        assert login.json()["must_change_password"] is True
        headers = {"Authorization": f'Bearer {login.json()["access_token"]}'}
        blocked = client.get("/actor/me/schedule", headers=headers)
        assert blocked.status_code == 428
        assert blocked.json()["detail"] == "password_change_required"
    finally:
        app.dependency_overrides.clear()


def test_actor_changes_initial_password_and_can_access_business_routes(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        theater = client.post(
            "/admin/theaters", headers=_admin_headers(), json={"name": "西安幽州剧场"}
        ).json()
        delivery = client.post(
            "/admin/actors",
            headers=_admin_headers(),
            json={
                "display_name": "小A",
                "phone_number": "13800138000",
                "entry_theater_id": theater["id"],
                "theater_ids": [theater["id"]],
            },
        ).json()["credential_delivery"]
        login = client.post(
            "/auth/login",
            json={"identifier": delivery["username"], "password": delivery["initial_password"]},
        ).json()
        changed = client.post(
            "/actor/me/password",
            headers={"Authorization": f'Bearer {login["access_token"]}'},
            json={"current_password": delivery["initial_password"], "new_password": "Secure123456"},
        )
        assert changed.status_code == 200
        relogin = client.post(
            "/auth/login",
            json={"identifier": delivery["username"], "password": "Secure123456"},
        ).json()
        assert relogin["must_change_password"] is False
        headers = {"Authorization": f'Bearer {relogin["access_token"]}'}
        assert client.get("/actor/me/schedule", headers=headers).status_code == 200
        profile = client.get("/actor/me/profile", headers=headers).json()
        assert profile["display_name"] == "小A"
        assert profile["phone_number"] == "13800138000"
        assert profile["theaters"][0]["name"] == "西安幽州剧场"
    finally:
        app.dependency_overrides.clear()


def test_admin_reset_password_forces_change_and_returns_fresh_pdf(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        theater = client.post(
            "/admin/theaters", headers=_admin_headers(), json={"name": "西安幽州剧场"}
        ).json()
        created = client.post(
            "/admin/actors",
            headers=_admin_headers(),
            json={
                "display_name": "小A",
                "phone_number": "13800138000",
                "entry_theater_id": theater["id"],
                "theater_ids": [theater["id"]],
            },
        ).json()
        reset = client.post(
            f'/admin/actors/{created["actor"]["id"]}/reset-password',
            headers=_admin_headers(),
            json={"entry_theater_id": theater["id"]},
        )
        assert reset.status_code == 200
        assert reset.json()["initial_password"] != created["credential_delivery"]["initial_password"]
        assert base64.b64decode(reset.json()["pdf_base64"]).startswith(b"%PDF")
        login = client.post(
            "/auth/login",
            json={
                "identifier": reset.json()["username"],
                "password": reset.json()["initial_password"],
            },
        ).json()
        assert login["must_change_password"] is True
    finally:
        app.dependency_overrides.clear()
