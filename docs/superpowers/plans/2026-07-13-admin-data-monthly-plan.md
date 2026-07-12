# Admin Data and Monthly Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persistent admin foundation for V1: theaters, roles, actors, actor role capabilities, actor ratings, leave review, and monthly performance generation.

**Architecture:** Extend the existing FastAPI backend with focused admin CRUD routes backed by SQLAlchemy models that already exist. Keep business operations in small services and keep routes as HTTP adapters. Extend the React admin shell from static placeholder pages into simple data-entry screens that call the new APIs.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, MySQL 8.0 for production and local integration, SQLite in-memory only for unit tests, pytest, TypeScript, React, Vite, Vitest.

## Global Constraints

- V1 users are administrators/schedulers and actors; V1 does not include a player login portal.
- V1 assumes every valid performance has the same fixed role list.
- Leave requests are full-day only.
- Scheduling is monthly for base capacity and weekly for generation/publishing.
- Hard rules outrank all preferences.
- MySQL 8.0 is the official database target.
- SQLite is allowed only for in-memory unit tests that do not validate database-specific SQL behavior.
- SQLAlchemy models must use portable column types unless a MySQL-specific behavior is explicitly tested.
- Keep generated files out of git: `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `*.egg-info/`.
- Commit each completed task.

---

## File Structure

Create or modify these files:

```text
backend/app/schemas/admin.py
backend/app/services/admin_data.py
backend/app/services/monthly_plan.py
backend/app/api/routes/admin.py
backend/migrations/versions/0002_add_monthly_plan_support.py
backend/tests/test_admin_api.py
backend/tests/test_monthly_plan_api.py
frontend/src/api/client.ts
frontend/src/components/AppShell.tsx
frontend/src/pages/admin/DashboardPage.tsx
frontend/src/pages/admin/MonthlyPlanPage.tsx
frontend/src/pages/admin/RequestsPage.tsx
frontend/src/pages/admin/SettingsPage.tsx
frontend/src/pages/admin/ActorsPage.tsx
frontend/tests/admin-workflows.test.tsx
```

Backend boundaries:

- `schemas/admin.py`: request/response Pydantic models for admin CRUD and monthly plan APIs.
- `services/admin_data.py`: reusable data operations for theaters, roles, actors, capabilities, leave review.
- `services/monthly_plan.py`: creates and cancels monthly performances from theater templates and closed dates.
- `api/routes/admin.py`: HTTP routing, auth dependency, request/response conversion only.

Frontend boundaries:

- `api/client.ts`: typed API methods.
- `SettingsPage.tsx`: theater and role setup.
- `ActorsPage.tsx`: actors, capabilities, ratings, limits.
- `MonthlyPlanPage.tsx`: month selection, closed dates, generate performances.
- `RequestsPage.tsx`: leave approval/rejection.

---

### Task 1: Admin Schemas and Data Services

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/services/admin_data.py`
- Test: `backend/tests/test_admin_api.py`

**Interfaces:**
- Produces `TheaterCreate`, `TheaterRead`, `RoleCreate`, `RoleRead`, `ActorCreate`, `ActorRead`, `ActorUpdate`, `CapabilityUpdate`, `LeaveReviewInput`.
- Produces `create_theater(db, payload) -> Theater`
- Produces `list_theaters(db) -> list[Theater]`
- Produces `create_role(db, payload) -> Role`
- Produces `list_roles(db) -> list[Role]`
- Produces `create_actor(db, payload) -> Actor`
- Produces `update_actor(db, actor_id, payload) -> Actor`
- Produces `replace_actor_capabilities(db, actor_id, role_ids) -> Actor`
- Produces `review_leave_request(db, leave_id, status) -> LeaveRequest`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_admin_api.py`:

```python
from app.models.enums import LeaveStatus, RatingLevel
from datetime import date

from app.models.entities import LeaveRequest
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


def test_admin_data_services_create_theaters_roles_and_actor_capabilities(db_session):
    theater = create_theater(
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
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_admin_api.py -q
```

Expected: FAIL with missing `app.schemas.admin` or `app.services.admin_data`.

- [ ] **Step 3: Implement admin schemas**

Create `backend/app/schemas/admin.py`:

```python
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LeaveStatus, PerformanceStatus, RatingLevel


class TheaterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    default_weekly_template: dict[str, list[str]]


class TheaterRead(TheaterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_name: str | None = None


class RoleRead(RoleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ActorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    max_consecutive_performances: int = Field(default=3, ge=1, le=3)
    rating_level: RatingLevel = RatingLevel.NORMAL
    low_rating_monthly_cap: int | None = Field(default=None, ge=0)
    notes: str | None = None


class ActorUpdate(BaseModel):
    max_consecutive_performances: int = Field(ge=1, le=3)
    rating_level: RatingLevel
    low_rating_monthly_cap: int | None = Field(default=None, ge=0)
    notes: str | None = None


class CapabilityUpdate(BaseModel):
    role_ids: list[int]


class ActorRead(BaseModel):
    id: int
    display_name: str
    max_consecutive_performances: int
    rating_level: RatingLevel
    low_rating_monthly_cap: int | None
    notes: str | None
    role_ids: list[int]


class LeaveReviewInput(BaseModel):
    status: LeaveStatus


class LeaveRead(BaseModel):
    id: int
    actor_id: int
    actor_name: str
    leave_date: date
    status: LeaveStatus
    note: str | None


class MonthlyPlanRequest(BaseModel):
    theater_id: int
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    closed_dates: list[date] = []


class PerformanceRead(BaseModel):
    id: int
    theater_id: int
    performance_date: date
    slot: str
    status: PerformanceStatus


class DashboardRead(BaseModel):
    pending_leave_requests: int
    pending_designations: int
    approval_required_assignments: int
    unpublished_performances: int
```

- [ ] **Step 4: Implement admin data services**

Create `backend/app/services/admin_data.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Actor, ActorRoleCapability, LeaveRequest, Role, Theater
from app.models.enums import LeaveStatus
from app.schemas.admin import ActorCreate, ActorUpdate, RoleCreate, TheaterCreate


def create_theater(db: Session, payload: TheaterCreate) -> Theater:
    theater = Theater(name=payload.name, default_weekly_template=payload.default_weekly_template)
    db.add(theater)
    db.commit()
    db.refresh(theater)
    return theater


def list_theaters(db: Session) -> list[Theater]:
    return list(db.scalars(select(Theater).order_by(Theater.id)))


def create_role(db: Session, payload: RoleCreate) -> Role:
    role = Role(name=payload.name, group_name=payload.group_name)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.id)))


def create_actor(db: Session, payload: ActorCreate) -> Actor:
    actor = Actor(
        display_name=payload.display_name,
        max_consecutive_performances=payload.max_consecutive_performances,
        rating_level=payload.rating_level,
        low_rating_monthly_cap=payload.low_rating_monthly_cap,
        notes=payload.notes,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def list_actors(db: Session) -> list[Actor]:
    statement = select(Actor).options(selectinload(Actor.role_capabilities)).order_by(Actor.id)
    return list(db.scalars(statement))


def update_actor(db: Session, actor_id: int, payload: ActorUpdate) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise LookupError("actor_not_found")
    actor.max_consecutive_performances = payload.max_consecutive_performances
    actor.rating_level = payload.rating_level
    actor.low_rating_monthly_cap = payload.low_rating_monthly_cap
    actor.notes = payload.notes
    db.commit()
    db.refresh(actor)
    return actor


def replace_actor_capabilities(db: Session, actor_id: int, role_ids: list[int]) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise LookupError("actor_not_found")
    for capability in list(actor.role_capabilities):
        db.delete(capability)
    db.flush()
    for role_id in sorted(set(role_ids)):
        if db.get(Role, role_id) is None:
            raise LookupError("role_not_found")
        db.add(ActorRoleCapability(actor_id=actor_id, role_id=role_id))
    db.commit()
    db.refresh(actor)
    return actor


def list_leave_requests(db: Session, status: LeaveStatus | None = None) -> list[LeaveRequest]:
    statement = select(LeaveRequest).options(selectinload(LeaveRequest.actor)).order_by(LeaveRequest.leave_date)
    if status is not None:
        statement = statement.where(LeaveRequest.status == status)
    return list(db.scalars(statement))


def review_leave_request(db: Session, leave_id: int, status: LeaveStatus) -> LeaveRequest:
    if status not in {LeaveStatus.APPROVED, LeaveStatus.REJECTED, LeaveStatus.LOCKED}:
        raise ValueError("review_status_must_be_final")
    leave = db.get(LeaveRequest, leave_id)
    if leave is None:
        raise LookupError("leave_not_found")
    leave.status = status
    db.commit()
    db.refresh(leave)
    return leave
```

- [ ] **Step 5: Run service tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_admin_api.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/services/admin_data.py backend/tests/test_admin_api.py
git commit -m "feat: add admin data services"
```

---

### Task 2: Admin CRUD API Routes

**Files:**
- Modify: `backend/app/api/routes/admin.py`
- Modify: `backend/tests/test_admin_api.py`

**Interfaces:**
- Produces `GET /admin/theaters`
- Produces `POST /admin/theaters`
- Produces `GET /admin/roles`
- Produces `POST /admin/roles`
- Produces `GET /admin/actors`
- Produces `POST /admin/actors`
- Produces `PATCH /admin/actors/{actor_id}`
- Produces `PUT /admin/actors/{actor_id}/capabilities`
- Produces `GET /admin/leave-requests`
- Produces `POST /admin/leave-requests/{leave_id}/review`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_admin_api.py`:

```python
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.auth import create_access_token


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
        assert client.get("/admin/actors", headers=headers).json()[0]["role_ids"] == [role_response.json()["id"]]
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_admin_api.py::test_admin_crud_routes_create_and_list_core_data -q
```

Expected: FAIL with 404 for missing admin CRUD routes.

- [ ] **Step 3: Implement admin route helpers and CRUD routes**

Replace `backend/app/api/routes/admin.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import Actor, LeaveRequest, Role, Theater
from app.models.enums import LeaveStatus
from app.schemas.admin import (
    ActorCreate,
    ActorRead,
    ActorUpdate,
    CapabilityUpdate,
    DashboardRead,
    LeaveRead,
    LeaveReviewInput,
    RoleCreate,
    RoleRead,
    TheaterCreate,
    TheaterRead,
)
from app.services.admin_data import (
    create_actor,
    create_role,
    create_theater,
    list_actors,
    list_leave_requests,
    list_roles,
    list_theaters,
    replace_actor_capabilities,
    review_leave_request,
    update_actor,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(_: dict[str, str] = Depends(require_admin)) -> DashboardRead:
    return DashboardRead(
        pending_leave_requests=0,
        pending_designations=0,
        approval_required_assignments=0,
        unpublished_performances=0,
    )


@router.get("/theaters", response_model=list[TheaterRead])
def get_theaters(_: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)) -> list[Theater]:
    return list_theaters(db)


@router.post("/theaters", response_model=TheaterRead)
def post_theater(
    payload: TheaterCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Theater:
    return create_theater(db, payload)


@router.get("/roles", response_model=list[RoleRead])
def get_roles(_: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)) -> list[Role]:
    return list_roles(db)


@router.post("/roles", response_model=RoleRead)
def post_role(
    payload: RoleCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Role:
    return create_role(db, payload)


@router.get("/actors", response_model=list[ActorRead])
def get_actors(_: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)) -> list[ActorRead]:
    return [_actor_read(actor) for actor in list_actors(db)]


@router.post("/actors", response_model=ActorRead)
def post_actor(
    payload: ActorCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    return _actor_read(create_actor(db, payload))


@router.patch("/actors/{actor_id}", response_model=ActorRead)
def patch_actor(
    actor_id: int,
    payload: ActorUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    try:
        return _actor_read(update_actor(db, actor_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/actors/{actor_id}/capabilities", response_model=ActorRead)
def put_actor_capabilities(
    actor_id: int,
    payload: CapabilityUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    try:
        return _actor_read(replace_actor_capabilities(db, actor_id, payload.role_ids))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/leave-requests", response_model=list[LeaveRead])
def get_leave_requests(
    status: LeaveStatus | None = None,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LeaveRead]:
    return [_leave_read(leave) for leave in list_leave_requests(db, status)]


@router.post("/leave-requests/{leave_id}/review", response_model=LeaveRead)
def post_leave_review(
    leave_id: int,
    payload: LeaveReviewInput,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LeaveRead:
    try:
        return _leave_read(review_leave_request(db, leave_id, payload.status))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _actor_read(actor: Actor) -> ActorRead:
    return ActorRead(
        id=actor.id,
        display_name=actor.display_name,
        max_consecutive_performances=actor.max_consecutive_performances,
        rating_level=actor.rating_level,
        low_rating_monthly_cap=actor.low_rating_monthly_cap,
        notes=actor.notes,
        role_ids=[capability.role_id for capability in actor.role_capabilities],
    )


def _leave_read(leave: LeaveRequest) -> LeaveRead:
    return LeaveRead(
        id=leave.id,
        actor_id=leave.actor_id,
        actor_name=leave.actor.display_name,
        leave_date=leave.leave_date,
        status=leave.status,
        note=leave.note,
    )
```

- [ ] **Step 4: Run API tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_admin_api.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/admin.py backend/tests/test_admin_api.py
git commit -m "feat: expose admin CRUD APIs"
```

---

### Task 3: Monthly Plan Generation API

**Files:**
- Create: `backend/app/services/monthly_plan.py`
- Modify: `backend/app/api/routes/admin.py`
- Create: `backend/tests/test_monthly_plan_api.py`

**Interfaces:**
- Produces `generate_monthly_plan(db, theater_id, year, month, closed_dates) -> list[Performance]`
- Produces `POST /admin/monthly-plan/generate`
- Produces `GET /admin/performances?year=&month=`

- [ ] **Step 1: Write failing monthly plan tests**

Create `backend/tests/test_monthly_plan_api.py`:

```python
from datetime import date

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
            json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": ["2026-06-02"]},
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
```

- [ ] **Step 2: Run monthly plan test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_monthly_plan_api.py -q
```

Expected: FAIL with missing monthly plan route/service.

- [ ] **Step 3: Implement monthly plan service**

Create `backend/app/services/monthly_plan.py`:

```python
from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.models.entities import Performance, Theater
from app.models.enums import PerformanceStatus
from app.services.calendar import generate_month_performances


def generate_monthly_plan(
    db: Session,
    theater_id: int,
    year: int,
    month: int,
    closed_dates: set[date],
) -> list[Performance]:
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")

    existing = db.scalars(
        select(Performance).where(
            Performance.theater_id == theater_id,
            extract("year", Performance.performance_date) == year,
            extract("month", Performance.performance_date) == month,
        )
    ).all()
    for performance in existing:
        db.delete(performance)
    db.flush()

    drafts = generate_month_performances(year, month, theater.default_weekly_template, closed_dates)
    performances = [
        Performance(
            theater_id=theater_id,
            performance_date=draft.date,
            slot=draft.slot,
            status=PerformanceStatus.DRAFT,
        )
        for draft in drafts
    ]
    db.add_all(performances)
    db.commit()
    for performance in performances:
        db.refresh(performance)
    return performances


def list_month_performances(db: Session, year: int, month: int) -> list[Performance]:
    statement = (
        select(Performance)
        .where(
            extract("year", Performance.performance_date) == year,
            extract("month", Performance.performance_date) == month,
        )
        .order_by(Performance.performance_date, Performance.slot)
    )
    return list(db.scalars(statement))
```

- [ ] **Step 4: Add monthly plan routes**

Modify `backend/app/api/routes/admin.py` imports:

```python
from app.schemas.admin import (..., MonthlyPlanRequest, PerformanceRead, ...)
from app.services.monthly_plan import generate_monthly_plan, list_month_performances
```

Add routes before helper functions:

```python
@router.post("/monthly-plan/generate", response_model=list[PerformanceRead])
def post_monthly_plan_generate(
    payload: MonthlyPlanRequest,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    try:
        return generate_monthly_plan(db, payload.theater_id, payload.year, payload.month, set(payload.closed_dates))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/performances", response_model=list[PerformanceRead])
def get_performances(
    year: int,
    month: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    return list_month_performances(db, year, month)
```

- [ ] **Step 5: Run monthly plan tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_monthly_plan_api.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monthly_plan.py backend/app/api/routes/admin.py backend/tests/test_monthly_plan_api.py
git commit -m "feat: generate persisted monthly plans"
```

---

### Task 4: Migration Update for Monthly Plan Indexes

**Files:**
- Create: `backend/migrations/versions/0002_add_monthly_plan_support.py`
- Test: `backend/tests/test_migration_files.py`

**Interfaces:**
- Produces a migration adding a unique index for `performances(theater_id, performance_date, slot)`.

- [ ] **Step 1: Write migration smoke test**

Create `backend/tests/test_migration_files.py`:

```python
from pathlib import Path


def test_monthly_plan_migration_declares_unique_performance_slot_index():
    migration = Path("migrations/versions/0002_add_monthly_plan_support.py").read_text()

    assert "uq_performance_theater_date_slot" in migration
    assert "theater_id" in migration
    assert "performance_date" in migration
    assert "slot" in migration
```

- [ ] **Step 2: Run migration smoke test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_migration_files.py -q
```

Expected: FAIL because migration file does not exist.

- [ ] **Step 3: Add migration**

Create `backend/migrations/versions/0002_add_monthly_plan_support.py`:

```python
"""add monthly plan support

Revision ID: 0002_add_monthly_plan_support
Revises: 0001_initial_schema
Create Date: 2026-07-13
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_monthly_plan_support"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_performance_theater_date_slot",
        "performances",
        ["theater_id", "performance_date", "slot"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_performance_theater_date_slot", "performances", type_="unique")
```

- [ ] **Step 4: Run migration smoke test and verify it passes**

Run:

```bash
cd backend && pytest tests/test_migration_files.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/0002_add_monthly_plan_support.py backend/tests/test_migration_files.py
git commit -m "feat: add monthly plan migration"
```

---

### Task 5: Frontend API Client and Admin Navigation

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/pages/admin/SettingsPage.tsx`
- Create: `frontend/src/pages/admin/ActorsPage.tsx`
- Modify: `frontend/tests/admin-workflows.test.tsx`

**Interfaces:**
- Produces `apiClient.getTheaters()`
- Produces `apiClient.createTheater(payload)`
- Produces `apiClient.getRoles()`
- Produces `apiClient.createRole(payload)`
- Produces `apiClient.getActors()`
- Produces `apiClient.createActor(payload)`
- Adds admin navigation items `基础配置` and `演员管理`.

- [ ] **Step 1: Write failing frontend workflow test**

Create `frontend/tests/admin-workflows.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { expect, test, vi } from "vitest";
import App from "../src/App";

test("admin shell exposes settings and actor management pages", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (url.endsWith("/admin/theaters")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/roles")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/actors")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("基础配置")).toBeInTheDocument());
  fireEvent.click(screen.getByText("基础配置"));
  expect(await screen.findByText("剧场配置")).toBeInTheDocument();
  fireEvent.click(screen.getByText("演员管理"));
  expect(await screen.findByText("新增演员")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run frontend workflow test and verify it fails**

Run:

```bash
cd frontend && npm run test -- --run tests/admin-workflows.test.tsx
```

Expected: FAIL because settings and actor pages do not exist.

- [ ] **Step 3: Extend API client**

Modify `frontend/src/api/client.ts`:

```ts
export type Theater = { id: number; name: string; default_weekly_template: Record<string, string[]> };
export type Role = { id: number; name: string; group_name: string | null };
export type Actor = {
  id: number;
  display_name: string;
  max_consecutive_performances: number;
  rating_level: "high" | "normal" | "low" | "suspended";
  low_rating_monthly_cap: number | null;
  notes: string | null;
  role_ids: number[];
};

export class ApiClient {
  constructor(private readonly baseUrl = "http://localhost:8000") {}

  async login(email: string, password: string): Promise<{ access_token: string; role: "admin" | "actor" }> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error("登录失败");
    return response.json();
  }

  async getTheaters(token: string): Promise<Theater[]> {
    return this.get("/admin/theaters", token);
  }

  async createTheater(token: string, payload: { name: string; default_weekly_template: Record<string, string[]> }): Promise<Theater> {
    return this.post("/admin/theaters", token, payload);
  }

  async getRoles(token: string): Promise<Role[]> {
    return this.get("/admin/roles", token);
  }

  async createRole(token: string, payload: { name: string; group_name: string | null }): Promise<Role> {
    return this.post("/admin/roles", token, payload);
  }

  async getActors(token: string): Promise<Actor[]> {
    return this.get("/admin/actors", token);
  }

  async createActor(token: string, payload: Omit<Actor, "id" | "role_ids">): Promise<Actor> {
    return this.post("/admin/actors", token, payload);
  }

  private async get<T>(path: string, token: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("请求失败");
    return response.json();
  }

  private async post<T>(path: string, token: string, payload: object): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("保存失败");
    return response.json();
  }
}

export const apiClient = new ApiClient();
```

- [ ] **Step 4: Add settings and actors pages**

Create `frontend/src/pages/admin/SettingsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { apiClient, Role, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function SettingsPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getTheaters(token).then(setTheaters);
    void apiClient.getRoles(token).then(setRoles);
  }, [token]);

  return (
    <section>
      <h2>基础配置</h2>
      <h3>剧场配置</h3>
      <ul>{theaters.map((theater) => <li key={theater.id}>{theater.name}</li>)}</ul>
      <h3>角色配置</h3>
      <ul>{roles.map((role) => <li key={role.id}>{role.name}</li>)}</ul>
    </section>
  );
}
```

Create `frontend/src/pages/admin/ActorsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Actor, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function ActorsPage() {
  const { token } = useAuth();
  const [actors, setActors] = useState<Actor[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getActors(token).then(setActors);
  }, [token]);

  return (
    <section>
      <h2>演员管理</h2>
      <button className="button" type="button">新增演员</button>
      <ul>{actors.map((actor) => <li key={actor.id}>{actor.display_name}</li>)}</ul>
    </section>
  );
}
```

- [ ] **Step 5: Wire navigation**

Modify `frontend/src/components/AppShell.tsx` imports:

```tsx
import { ActorsPage } from "../pages/admin/ActorsPage";
import { SettingsPage } from "../pages/admin/SettingsPage";
```

Modify `adminItems`:

```tsx
const adminItems = [
  ["工作台", Home],
  ["基础配置", CalendarDays],
  ["演员管理", UserRound],
  ["月度计划", CalendarDays],
  ["请假审核", ClipboardList],
  ["周排班", ClipboardList],
] as const;
```

Modify `renderPage`:

```tsx
if (page === "基础配置") return <SettingsPage />;
if (page === "演员管理") return <ActorsPage />;
```

- [ ] **Step 6: Run frontend workflow test and verify it passes**

Run:

```bash
cd frontend && npm run test -- --run tests/admin-workflows.test.tsx
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/AppShell.tsx frontend/src/pages/admin/SettingsPage.tsx frontend/src/pages/admin/ActorsPage.tsx frontend/tests/admin-workflows.test.tsx
git commit -m "feat: add admin data management UI shell"
```

---

### Task 6: Monthly Plan Frontend and Leave Review UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/admin/MonthlyPlanPage.tsx`
- Modify: `frontend/src/pages/admin/RequestsPage.tsx`
- Modify: `frontend/tests/admin-workflows.test.tsx`

**Interfaces:**
- Produces `apiClient.generateMonthlyPlan(token, payload)`
- Produces `apiClient.getPerformances(token, year, month)`
- Produces `apiClient.getLeaveRequests(token)`
- Produces `apiClient.reviewLeaveRequest(token, leaveId, status)`

- [ ] **Step 1: Add failing monthly plan UI test**

Append to `frontend/tests/admin-workflows.test.tsx`:

```tsx
test("monthly plan page loads theaters and performances", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      if (url.endsWith("/admin/theaters")) return new Response(JSON.stringify([{ id: 1, name: "西幽剧场", default_weekly_template: {} }]), { status: 200 });
      if (url.includes("/admin/performances")) return new Response(JSON.stringify([{ id: 1, theater_id: 1, performance_date: "2026-06-01", slot: "early", status: "draft" }]), { status: 200 });
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("月度计划")).toBeInTheDocument());
  fireEvent.click(screen.getByText("月度计划"));
  expect(await screen.findByText("西幽剧场")).toBeInTheDocument();
  expect(await screen.findByText("2026-06-01 early")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run monthly plan UI test and verify it fails**

Run:

```bash
cd frontend && npm run test -- --run tests/admin-workflows.test.tsx
```

Expected: FAIL because monthly plan page does not call APIs.

- [ ] **Step 3: Extend API client**

Append types and methods to `frontend/src/api/client.ts`:

```ts
export type Performance = {
  id: number;
  theater_id: number;
  performance_date: string;
  slot: string;
  status: string;
};

export type LeaveRequest = {
  id: number;
  actor_id: number;
  actor_name: string;
  leave_date: string;
  status: string;
  note: string | null;
};
```

Add methods inside `ApiClient`:

```ts
async generateMonthlyPlan(token: string, payload: { theater_id: number; year: number; month: number; closed_dates: string[] }): Promise<Performance[]> {
  return this.post("/admin/monthly-plan/generate", token, payload);
}

async getPerformances(token: string, year: number, month: number): Promise<Performance[]> {
  return this.get(`/admin/performances?year=${year}&month=${month}`, token);
}

async getLeaveRequests(token: string): Promise<LeaveRequest[]> {
  return this.get("/admin/leave-requests", token);
}

async reviewLeaveRequest(token: string, leaveId: number, status: "approved" | "rejected" | "locked"): Promise<LeaveRequest> {
  return this.post(`/admin/leave-requests/${leaveId}/review`, token, { status });
}
```

- [ ] **Step 4: Implement monthly plan page**

Replace `frontend/src/pages/admin/MonthlyPlanPage.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { apiClient, Performance, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function MonthlyPlanPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [performances, setPerformances] = useState<Performance[]>([]);
  const [year] = useState(2026);
  const [month] = useState(6);

  useEffect(() => {
    if (!token) return;
    void apiClient.getTheaters(token).then(setTheaters);
    void apiClient.getPerformances(token, year, month).then(setPerformances);
  }, [token, year, month]);

  return (
    <section>
      <h2>月度计划</h2>
      <div className="panel">
        <h3>剧场</h3>
        <ul>{theaters.map((theater) => <li key={theater.id}>{theater.name}</li>)}</ul>
      </div>
      <div className="panel">
        <h3>本月场次</h3>
        <ul>{performances.map((performance) => <li key={performance.id}>{performance.performance_date} {performance.slot}</li>)}</ul>
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Implement leave review page**

Replace `frontend/src/pages/admin/RequestsPage.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { apiClient, LeaveRequest } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function RequestsPage() {
  const { token } = useAuth();
  const [requests, setRequests] = useState<LeaveRequest[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getLeaveRequests(token).then(setRequests);
  }, [token]);

  async function review(leaveId: number, status: "approved" | "rejected") {
    if (!token) return;
    await apiClient.reviewLeaveRequest(token, leaveId, status);
    setRequests(await apiClient.getLeaveRequests(token));
  }

  return (
    <section>
      <h2>请假审核</h2>
      <ul>
        {requests.map((request) => (
          <li key={request.id}>
            {request.actor_name} {request.leave_date} {request.status}
            <button className="button" type="button" onClick={() => review(request.id, "approved")}>批准</button>
            <button className="button" type="button" onClick={() => review(request.id, "rejected")}>拒绝</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 6: Run frontend tests and build**

Run:

```bash
cd frontend && npm run test -- --run && npm run build
```

Expected: frontend tests and build pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/admin/MonthlyPlanPage.tsx frontend/src/pages/admin/RequestsPage.tsx frontend/tests/admin-workflows.test.tsx
git commit -m "feat: connect monthly plan and leave review UI"
```

---

### Task 7: Final Verification

**Files:**
- Modify: `docs/superpowers/acceptance-checklist.md`

**Interfaces:**
- Produces updated checklist marking admin foundation scope as complete.

- [ ] **Step 1: Run backend checks**

Run:

```bash
backend/.venv/bin/ruff check backend
cd backend && pytest -q
```

Expected: ruff passes and all backend tests pass.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
cd frontend && npm run test -- --run && npm run build
```

Expected: frontend tests and production build pass.

- [ ] **Step 3: Update acceptance checklist**

Modify `docs/superpowers/acceptance-checklist.md`:

```markdown
# 剧场卡司排班 V1 验收清单

- [x] 管理员可以登录。
- [x] 演员可以登录。
- [x] 系统可以生成月度场次草稿，支持每周不同早晚场模板。
- [x] 公休日期不会生成可排场次。
- [x] 演员整天请假会阻止当天所有排班。
- [x] 演员可出演多个角色，但同一场不能出演两个角色。
- [x] 默认 3 连、个人 2 连、个人 1 连限制可测试。
- [x] 指定优先级为万能指定 > 榜单前三指定 > 对位指定。
- [x] 指定失败会显示原因。
- [x] 许愿只影响补排，不压过指定。
- [x] 低评级月度上限会阻止发布或触发审批。
- [x] 群统计文本导入生成草稿确认数据，不直接写正式记录。
- [x] 演员可以提交整天请假。
- [x] 管理员可以看到周排班和待处理队列。

## Admin Foundation Added

- [x] 管理员可以维护剧场。
- [x] 管理员可以维护固定角色。
- [x] 管理员可以维护演员、评级、最大连场和低评级上限。
- [x] 管理员可以维护演员可出演角色。
- [x] 管理员可以审核演员整天请假。
- [x] 管理员可以生成并保存月度场次。

## Remaining V1 Work

- [ ] 指定/许愿正式录入、导入确认和周批次纳入。
- [ ] 周排班页面真实展示排班表、冲突和锁定/替换/重算。
- [ ] 发布前校验、发布状态和导出。
- [ ] MySQL 8.0 实例上的迁移和集成验证。
```

- [ ] **Step 4: Ensure generated files remain untracked**

Run:

```bash
git ls-files | rg '(__pycache__|\.pyc$|frontend/dist|egg-info|node_modules|backend/.venv)'
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/acceptance-checklist.md
git commit -m "docs: update admin foundation acceptance status"
```

---

## Self-Review

Spec coverage:

- Admin theater, role, actor, capability, rating, max consecutive, low rating cap management are covered by Tasks 1, 2, and 5.
- Leave review is covered by Tasks 1, 2, and 6.
- Monthly plan generation and closed dates are covered by Tasks 3 and 6.
- MySQL migration support is improved by Task 4.
- Frontend admin entry points are covered by Tasks 5 and 6.

Known boundaries:

- This plan does not implement designation/wish confirmation, weekly scheduling table UI, publish/export, or MySQL container/integration execution. Those remain the next phase after admin foundation data exists.
