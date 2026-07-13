from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_db
from app.main import app
from app.models.entities import LeaveRequest
from app.models.enums import LeaveStatus, RatingLevel
from app.schemas.admin import ActorCreate, ActorUpdate, RoleCreate, TheaterCreate
from app.services.admin_data import (
    create_actor,
    create_role,
    create_theater,
    list_roles,
    list_theaters,
    replace_actor_capabilities,
    review_leave_request,
    update_actor,
)
from app.services.auth import create_access_token


def test_admin_data_services_create_theaters_roles_and_actor_capabilities(db_session):
    create_theater(
        db_session,
        TheaterCreate(
            name="西幽剧场",
            default_weekly_template={"monday": ["early", "late"], "tuesday": ["late"]},
        ),
    )
    role = create_role(db_session, RoleCreate(name="长离", group_name="女位"))
    actor = create_actor(
        db_session,
        ActorCreate(
            display_name="小展",
            max_consecutive_performances=2,
            rating_level=RatingLevel.NORMAL,
            low_rating_monthly_cap=None,
            notes="可跨卡",
        ),
    )
    replace_actor_capabilities(db_session, actor.id, [role.id])

    assert [item.name for item in list_theaters(db_session)] == ["西幽剧场"]
    assert [item.name for item in list_roles(db_session)] == ["长离"]
    assert actor.role_capabilities[0].role.name == "长离"


def test_update_actor_rating_and_leave_review(db_session):
    actor = create_actor(
        db_session,
        ActorCreate(
            display_name="浩泽",
            max_consecutive_performances=3,
            rating_level=RatingLevel.NORMAL,
            low_rating_monthly_cap=None,
            notes=None,
        ),
    )
    updated = update_actor(
        db_session,
        actor.id,
        ActorUpdate(
            max_consecutive_performances=1,
            rating_level=RatingLevel.LOW,
            low_rating_monthly_cap=4,
            notes="观察期",
        ),
    )
    leave = LeaveRequest(actor_id=actor.id, leave_date=date(2026, 6, 5), note="提前请假")
    db_session.add(leave)
    db_session.commit()

    reviewed = review_leave_request(db_session, leave.id, LeaveStatus.APPROVED)

    assert updated.max_consecutive_performances == 1
    assert updated.rating_level == RatingLevel.LOW
    assert updated.low_rating_monthly_cap == 4
    assert reviewed.status == LeaveStatus.APPROVED


def test_admin_crud_routes_create_and_list_core_data(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        token = create_access_token("admin@example.com", "admin")
        headers = {"Authorization": f"Bearer {token}"}

        theater_response = client.post(
            "/admin/theaters",
            headers=headers,
            json={"name": "西幽剧场", "default_weekly_template": {"monday": ["early", "late"]}},
        )
        role_response = client.post(
            "/admin/roles",
            headers=headers,
            json={"name": "长离", "group_name": "女位"},
        )
        actor_response = client.post(
            "/admin/actors",
            headers=headers,
            json={
                "display_name": "小展",
                "max_consecutive_performances": 2,
                "rating_level": "normal",
                "low_rating_monthly_cap": None,
                "notes": "可跨卡",
            },
        )
        capability_response = client.put(
            f"/admin/actors/{actor_response.json()['id']}/capabilities",
            headers=headers,
            json={"role_ids": [role_response.json()["id"]]},
        )

        assert theater_response.status_code == 200
        assert role_response.status_code == 200
        assert actor_response.status_code == 200
        assert capability_response.status_code == 200
        assert client.get("/admin/theaters", headers=headers).json()[0]["name"] == "西幽剧场"
        assert client.get("/admin/actors", headers=headers).json()[0]["role_ids"] == [
            role_response.json()["id"]
        ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "template",
    [
        {"holiday": ["early"]},
        {"monday": ["noon"]},
        {"monday": ["early", "early"]},
    ],
)
def test_theater_template_rejects_invalid_keys_slots_and_duplicates(template):
    with pytest.raises(ValidationError):
        TheaterCreate(name="错误模板", default_weekly_template=template)


def test_invalid_capability_replacement_preserves_existing_roles(db_session):
    first = create_role(db_session, RoleCreate(name="长离", group_name=None))
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    replace_actor_capabilities(db_session, actor.id, [first.id])

    with pytest.raises(LookupError, match="role_not_found"):
        replace_actor_capabilities(db_session, actor.id, [999])
    db_session.commit()
    db_session.refresh(actor)

    assert [item.role_id for item in actor.role_capabilities] == [first.id]
