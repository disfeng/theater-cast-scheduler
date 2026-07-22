from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import Theater, User, UserTheaterScope
from app.models.enums import UserRole
from app.services.auth import create_access_token


def _client(db_session):
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    return TestClient(app)


def _headers(user):
    token = create_access_token(user.email, user.role.value, user_id=user.id)
    return {"Authorization": f"Bearer {token}"}


def test_theater_admin_only_lists_authorized_theaters(db_session):
    root = User(
        email="root@test", display_name="Root", password_hash="x", role=UserRole.SUPER_ADMIN
    )
    manager = User(
        email="manager@test", display_name="Manager", password_hash="x", role=UserRole.THEATER_ADMIN
    )
    first, second = Theater(name="授权剧场"), Theater(name="隐藏剧场")
    db_session.add_all([root, manager, first, second])
    db_session.flush()
    db_session.add(
        UserTheaterScope(user_id=manager.id, theater_id=first.id, granted_by_user_id=root.id)
    )
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.get("/admin/theaters", headers=_headers(manager))
        assert response.status_code == 200
        assert [row["name"] for row in response.json()] == ["授权剧场"]
        forbidden = client.get(f"/admin/theaters/{second.id}/slots", headers=_headers(manager))
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "theater_scope_forbidden"
    finally:
        app.dependency_overrides.clear()


def test_super_admin_creates_scoped_manager_and_audit_log(db_session):
    root = User(
        email="root@test", display_name="Root", password_hash="x", role=UserRole.SUPER_ADMIN
    )
    theater = Theater(name="西安幽州剧场")
    db_session.add_all([root, theater])
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.post(
            "/admin/administrator-accounts",
            headers=_headers(root),
            json={
                "email": "manager@test",
                "display_name": "店长",
                "password": "password-123",
                "role": "theater_admin",
                "theater_ids": [theater.id],
            },
        )
        assert response.status_code == 200
        assert response.json()["theater_ids"] == [theater.id]
        logs = client.get("/admin/audit-logs?module=administrator_accounts", headers=_headers(root))
        assert logs.status_code == 200
        assert logs.json()[0]["action"] == "create"
        assert logs.json()[0]["after_data"]["email"] == "manager@test"
    finally:
        app.dependency_overrides.clear()


def test_theater_admin_cannot_manage_administrator_accounts(db_session):
    manager = User(
        email="manager@test", display_name="Manager", password_hash="x", role=UserRole.THEATER_ADMIN
    )
    db_session.add(manager)
    db_session.commit()
    client = _client(db_session)
    try:
        response = client.get("/admin/administrator-accounts", headers=_headers(manager))
        assert response.status_code == 403
        assert response.json()["detail"] == "super_admin_required"
    finally:
        app.dependency_overrides.clear()
