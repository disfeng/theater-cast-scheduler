from datetime import date, time

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import Actor, Designation, Performance, Role, Theater, TheaterSlot, User
from app.models.enums import DesignationType, UserRole
from app.services.auth import create_access_token


def _admin_client(db_session) -> TestClient:
    user = User(email="workspace-admin@example.com", password_hash="test", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(user.email, 'admin')}"
    return client


def test_month_workspace_route_returns_theater_performances(db_session):
    client = _admin_client(db_session)
    theater = Theater(name="月历剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 8, 5),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    db_session.add(performance)
    db_session.commit()
    try:
        response = client.get(
            f"/admin/designation-workspace/month?theater_id={theater.id}&year=2026&month=8"
        )
        assert response.status_code == 200
        assert response.json()["days"][0]["performances"][0]["id"] == performance.id
    finally:
        app.dependency_overrides.clear()


def test_month_workspace_route_rejects_missing_theater_and_unauthorized_access(db_session):
    client = _admin_client(db_session)
    try:
        missing = client.get("/admin/designation-workspace/month?theater_id=999&year=2026&month=8")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "剧场不存在"
        anonymous = TestClient(app).get(
            "/admin/designation-workspace/month?theater_id=999&year=2026&month=8"
        )
        assert anonymous.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_performance_workspace_route_returns_lazy_drawer_details(db_session):
    client = _admin_client(db_session)
    theater = Theater(name="抽屉剧场")
    slot = TheaterSlot(theater=theater, name="下午场", start_time=time(16, 0))
    role = Role(theater=theater, name="长离", group_name="女")
    actor = Actor(display_name="小展")
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 8, 5),
        slot_name_snapshot="下午场",
        start_time_snapshot=time(16, 0),
    )
    db_session.add_all([role, actor, performance])
    db_session.flush()
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jennifer",
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=performance.id,
        performance_id=performance.id,
        submitted_at=date(2026, 7, 17),
        lifecycle_status="draft",
    )
    db_session.add(designation)
    db_session.commit()
    try:
        response = client.get(f"/admin/designation-workspace/performances/{performance.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["performance"]["slot_name"] == "下午场"
        assert body["designations"][0]["id"] == designation.id
        assert body["players"] == []
        assert body["wishes"] == []
        assert body["conflicts"][0]["code"] == "ROLE_NOT_ALLOWED"
    finally:
        app.dependency_overrides.clear()
