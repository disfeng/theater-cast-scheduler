# Theater Cast Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a V1 theater cast scheduling web system with admin scheduling, actor leave submission, rule-based weekly schedule generation, import parsing, and publish/export flows.

**Architecture:** Use a tested backend-first architecture. FastAPI owns persistence, auth, scheduling rules, imports, and API contracts; React/Vite consumes those APIs for admin and actor workflows. The scheduling engine is a pure Python service with deterministic inputs and explanatory outputs so it can be tested independently from HTTP and UI code.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite for local dev with PostgreSQL-compatible schema choices, pytest, TypeScript, React, Vite, Vitest.

## Global Constraints

- V1 users are administrators/schedulers and actors; V1 does not include a player login portal.
- V1 assumes every valid performance has the same fixed role list.
- Leave requests are full-day only.
- Scheduling is monthly for base capacity and weekly for generation/publishing.
- Hard rules outrank all preferences.
- Paid designation priority is `universal > top_three > paired`.
- Designations cannot override hard rules.
- Wishes never outrank designations.
- Low-rated actor monthly caps require approval before publishing if exceeded.
- Default max consecutive performances is 3, with per-actor overrides of 2 or 1.
- Imported group text must go through a confirmation flow before becoming official records.
- The repository currently has no git metadata; initialize git before the first commit.

---

## File Structure

Create this structure:

```text
backend/
  app/
    __init__.py
    main.py
    core/config.py
    db/base.py
    db/session.py
    models/enums.py
    models/entities.py
    schemas/auth.py
    schemas/imports.py
    schemas/scheduling.py
    services/auth.py
    services/calendar.py
    services/import_parser.py
    services/rules.py
    services/scheduler.py
    api/deps.py
    api/routes/auth.py
    api/routes/admin.py
    api/routes/actor.py
    api/routes/scheduling.py
  pyproject.toml
  tests/
    conftest.py
    test_calendar.py
    test_import_parser.py
    test_rules.py
    test_scheduler.py
    test_api_smoke.py
frontend/
  index.html
  package.json
  tsconfig.json
  vite.config.ts
  src/
    main.tsx
    App.tsx
    api/client.ts
    auth/AuthContext.tsx
    components/AppShell.tsx
    pages/LoginPage.tsx
    pages/admin/DashboardPage.tsx
    pages/admin/MonthlyPlanPage.tsx
    pages/admin/RequestsPage.tsx
    pages/admin/WeeklySchedulingPage.tsx
    pages/actor/MySchedulePage.tsx
    pages/actor/MyLeavePage.tsx
    styles.css
  tests/
    scheduling-ui.test.tsx
README.md
```

Backend responsibilities:

- `models/entities.py`: database entities only.
- `services/rules.py`: hard-rule validation and explanation.
- `services/scheduler.py`: pure schedule generation.
- `services/import_parser.py`: group text parser returning draft records only.
- `api/routes/*`: HTTP boundary only.

Frontend responsibilities:

- `api/client.ts`: typed API wrapper.
- `auth/AuthContext.tsx`: session state and role switching.
- `pages/admin/*`: admin workflows.
- `pages/actor/*`: actor workflows.

---

### Task 1: Project Scaffolding and Tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/tests/test_api_smoke.py`
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `README.md`

**Interfaces:**
- Produces: `backend.app.main.app: FastAPI`
- Produces: frontend script commands `npm run dev`, `npm run test`, `npm run build`

- [ ] **Step 1: Initialize git**

Run:

```bash
git init
```

Expected: output contains `Initialized empty Git repository`.

- [ ] **Step 2: Create backend package and failing smoke test**

Create `backend/pyproject.toml`:

```toml
[project]
name = "theater-cast-scheduling-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "sqlalchemy>=2.0.30",
  "alembic>=1.13.0",
  "pydantic-settings>=2.4.0",
  "python-jose[cryptography]>=3.3.0",
  "passlib[bcrypt]>=1.7.4",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2.0",
  "httpx>=0.27.0",
  "ruff>=0.5.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

Create `backend/tests/test_api_smoke.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run backend test and verify it fails before app exists**

Run:

```bash
cd backend && pytest tests/test_api_smoke.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing `app.main`.

- [ ] **Step 4: Implement minimal FastAPI app**

Create `backend/app/core/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Theater Cast Scheduling"
    database_url: str = "sqlite:///./theater_cast_scheduling.db"
    jwt_secret: str = "local-dev-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480


settings = Settings()
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.core.config import settings


app = FastAPI(title=settings.app_name)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run backend test and verify it passes**

Run:

```bash
cd backend && pytest tests/test_api_smoke.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Create minimal frontend**

Create `frontend/package.json`:

```json
{
  "name": "theater-cast-scheduling-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0",
    "typescript": "^5.5.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "jsdom": "^25.0.0",
    "vitest": "^2.0.0"
  }
}
```

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>剧场卡司排班</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/App.tsx`:

```tsx
export default function App() {
  return <main>剧场卡司排班</main>;
}
```

Create `frontend/src/main.tsx`:

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Create `README.md`:

```markdown
# 剧场卡司排班

V1 theater cast scheduling system.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```
```

- [ ] **Step 7: Install dependencies and build frontend**

Run:

```bash
cd frontend && npm install && npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 8: Commit**

```bash
git add README.md backend frontend
git commit -m "chore: scaffold scheduling app"
```

---

### Task 2: Database Models and Test Fixtures

**Files:**
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/models/enums.py`
- Create: `backend/app/models/entities.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `Base`
- Produces: `SessionLocal`
- Produces enums `UserRole`, `PerformanceStatus`, `LeaveStatus`, `DesignationType`, `RatingLevel`
- Produces ORM models used by API and services

- [ ] **Step 1: Write failing model relationship tests**

Create `backend/tests/test_models.py`:

```python
from datetime import date

from app.models.entities import Actor, ActorRoleCapability, Role, Theater


def test_actor_can_have_multiple_role_capabilities(db_session):
    actor = Actor(display_name="小展", max_consecutive_performances=3)
    role_a = Role(name="长离", group_name="女位")
    role_b = Role(name="北恒", group_name="女位")
    db_session.add_all([actor, role_a, role_b])
    db_session.flush()

    db_session.add_all([
        ActorRoleCapability(actor_id=actor.id, role_id=role_a.id),
        ActorRoleCapability(actor_id=actor.id, role_id=role_b.id),
    ])
    db_session.commit()

    refreshed = db_session.get(Actor, actor.id)
    assert {cap.role.name for cap in refreshed.role_capabilities} == {"长离", "北恒"}


def test_theater_template_fields_are_persisted(db_session):
    theater = Theater(
        name="西幽剧场",
        default_weekly_template={
            "monday": ["early", "late"],
            "tuesday": ["late"],
        },
    )
    db_session.add(theater)
    db_session.commit()

    refreshed = db_session.get(Theater, theater.id)
    assert refreshed.name == "西幽剧场"
    assert refreshed.default_weekly_template["monday"] == ["early", "late"]
```

- [ ] **Step 2: Run model tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_models.py -q
```

Expected: FAIL with missing database modules or models.

- [ ] **Step 3: Implement database base, session, enums, and entities**

Create `backend/app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `backend/app/db/session.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

Create `backend/app/models/enums.py`:

```python
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    ACTOR = "actor"


class PerformanceStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class LeaveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    LOCKED = "locked"


class DesignationType(StrEnum):
    UNIVERSAL = "universal"
    TOP_THREE = "top_three"
    PAIRED = "paired"


class RatingLevel(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    SUSPENDED = "suspended"
```

Create `backend/app/models/entities.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DesignationType, LeaveStatus, PerformanceStatus, RatingLevel, UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("actors.id"), nullable=True)
    actor: Mapped["Actor | None"] = relationship(back_populates="user")


class Theater(Base):
    __tablename__ = "theaters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    default_weekly_template: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Actor(Base):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    max_consecutive_performances: Mapped[int] = mapped_column(Integer, default=3)
    rating_level: Mapped[RatingLevel] = mapped_column(Enum(RatingLevel), default=RatingLevel.NORMAL)
    low_rating_monthly_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[User | None] = relationship(back_populates="actor")
    role_capabilities: Mapped[list["ActorRoleCapability"]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )


class ActorRoleCapability(Base):
    __tablename__ = "actor_role_capabilities"
    __table_args__ = (UniqueConstraint("actor_id", "role_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor: Mapped[Actor] = relationship(back_populates="role_capabilities")
    role: Mapped[Role] = relationship()


class Performance(Base):
    __tablename__ = "performances"

    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"))
    performance_date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[PerformanceStatus] = mapped_column(
        Enum(PerformanceStatus), default=PerformanceStatus.DRAFT
    )
    theater: Mapped[Theater] = relationship()


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (UniqueConstraint("actor_id", "leave_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[LeaveStatus] = mapped_column(Enum(LeaveStatus), default=LeaveStatus.PENDING)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[Actor] = relationship()


class Designation(Base):
    __tablename__ = "designations"

    id: Mapped[int] = mapped_column(primary_key=True)
    designation_type: Mapped[DesignationType] = mapped_column(Enum(DesignationType), index=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    target_performance_id: Mapped[int | None] = mapped_column(ForeignKey("performances.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    included_in_batch: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
    target_performance: Mapped[Performance | None] = relationship()


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(String(120))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (UniqueConstraint("performance_id", "role_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    performance_id: Mapped[int] = mapped_column(ForeignKey("performances.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("actors.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    locked: Mapped[bool] = mapped_column(default=False)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    approved: Mapped[bool] = mapped_column(default=False)
    performance: Mapped[Performance] = relationship()
    role: Mapped[Role] = relationship()
    actor: Mapped[Actor] = relationship()
```

- [ ] **Step 4: Add in-memory database fixture**

Create `backend/tests/conftest.py`:

```python
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import entities  # noqa: F401


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 5: Run model tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_models.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db backend/app/models backend/tests
git commit -m "feat: add scheduling data model"
```

---

### Task 3: Calendar Generation

**Files:**
- Create: `backend/app/services/calendar.py`
- Create: `backend/tests/test_calendar.py`

**Interfaces:**
- Produces: `PerformanceDraft(date: date, slot: str)`
- Produces: `generate_month_performances(year: int, month: int, weekly_template: dict[str, list[str]], closed_dates: set[date]) -> list[PerformanceDraft]`

- [ ] **Step 1: Write failing calendar tests**

Create `backend/tests/test_calendar.py`:

```python
from datetime import date

from app.services.calendar import generate_month_performances


def test_generate_month_uses_weekly_template_and_closed_dates():
    template = {
        "monday": ["early", "late"],
        "tuesday": ["late"],
        "wednesday": ["late"],
        "thursday": ["late"],
        "friday": ["early", "late"],
        "saturday": ["early", "late"],
        "sunday": ["early", "late"],
    }

    drafts = generate_month_performances(
        year=2026,
        month=6,
        weekly_template=template,
        closed_dates={date(2026, 6, 2)},
    )

    june_1 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 1)]
    june_2 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 2)]
    june_3 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 3)]

    assert june_1 == ["early", "late"]
    assert june_2 == []
    assert june_3 == ["late"]
```

- [ ] **Step 2: Run calendar test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_calendar.py -q
```

Expected: FAIL with missing `app.services.calendar`.

- [ ] **Step 3: Implement calendar generation**

Create `backend/app/services/calendar.py`:

```python
from dataclasses import dataclass
from datetime import date
from calendar import monthrange


WEEKDAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


@dataclass(frozen=True)
class PerformanceDraft:
    date: date
    slot: str


def generate_month_performances(
    year: int,
    month: int,
    weekly_template: dict[str, list[str]],
    closed_dates: set[date],
) -> list[PerformanceDraft]:
    _, days_in_month = monthrange(year, month)
    drafts: list[PerformanceDraft] = []

    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        if current in closed_dates:
            continue
        weekday = WEEKDAY_NAMES[current.weekday()]
        for slot in weekly_template.get(weekday, []):
            drafts.append(PerformanceDraft(date=current, slot=slot))

    return drafts
```

- [ ] **Step 4: Run calendar test and verify it passes**

Run:

```bash
cd backend && pytest tests/test_calendar.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calendar.py backend/tests/test_calendar.py
git commit -m "feat: generate monthly performance drafts"
```

---

### Task 4: Hard Rule Engine

**Files:**
- Create: `backend/app/schemas/scheduling.py`
- Create: `backend/app/services/rules.py`
- Create: `backend/tests/test_rules.py`

**Interfaces:**
- Produces dataclasses `PerformanceSlot`, `AssignmentCandidate`, `RuleViolation`
- Produces `validate_candidate(candidate, existing_assignments, approved_leave_dates, actor_role_ids, monthly_counts, low_rating_caps) -> list[RuleViolation]`
- Produces `would_exceed_consecutive_limit(actor_id, target_slot, existing_slots, max_consecutive) -> bool`

- [ ] **Step 1: Write failing rule tests**

Create `backend/tests/test_rules.py`:

```python
from datetime import date

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot
from app.services.rules import validate_candidate, would_exceed_consecutive_limit


def test_candidate_fails_when_actor_is_on_leave():
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early"))

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={1: {date(2026, 6, 5)}},
        actor_role_ids={1: {10}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["actor_on_leave"]


def test_candidate_fails_when_actor_lacks_role_capability():
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=PerformanceSlot(1, date(2026, 6, 5), "early"))

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=[],
        approved_leave_dates={},
        actor_role_ids={1: {99}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["role_not_allowed"]


def test_same_actor_cannot_take_two_roles_in_same_performance():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")
    candidate = AssignmentCandidate(actor_id=1, role_id=10, performance=performance)
    existing = [AssignmentCandidate(actor_id=1, role_id=11, performance=performance)]

    violations = validate_candidate(
        candidate=candidate,
        existing_assignments=existing,
        approved_leave_dates={},
        actor_role_ids={1: {10, 11}},
        monthly_counts={},
        low_rating_caps={},
    )

    assert [violation.code for violation in violations] == ["actor_already_in_performance"]


def test_consecutive_limit_detects_fourth_link():
    existing_slots = [
        PerformanceSlot(1, date(2026, 6, 5), "early"),
        PerformanceSlot(2, date(2026, 6, 5), "late"),
        PerformanceSlot(3, date(2026, 6, 6), "early"),
    ]
    target = PerformanceSlot(4, date(2026, 6, 6), "late")

    assert would_exceed_consecutive_limit(1, target, {1: existing_slots}, max_consecutive=3)
```

- [ ] **Step 2: Run rule tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_rules.py -q
```

Expected: FAIL with missing schemas/services.

- [ ] **Step 3: Implement scheduling schemas and hard rules**

Create `backend/app/schemas/scheduling.py`:

```python
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PerformanceSlot:
    id: int
    date: date
    slot: str


@dataclass(frozen=True)
class AssignmentCandidate:
    actor_id: int
    role_id: int
    performance: PerformanceSlot


@dataclass(frozen=True)
class RuleViolation:
    code: str
    message: str
```

Create `backend/app/services/rules.py`:

```python
from datetime import date

from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot, RuleViolation


SLOT_ORDER = {"early": 0, "late": 1}


def validate_candidate(
    candidate: AssignmentCandidate,
    existing_assignments: list[AssignmentCandidate],
    approved_leave_dates: dict[int, set[date]],
    actor_role_ids: dict[int, set[int]],
    monthly_counts: dict[int, int],
    low_rating_caps: dict[int, int],
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []

    if candidate.performance.date in approved_leave_dates.get(candidate.actor_id, set()):
        violations.append(RuleViolation("actor_on_leave", "演员当天已批准请假"))

    if candidate.role_id not in actor_role_ids.get(candidate.actor_id, set()):
        violations.append(RuleViolation("role_not_allowed", "演员不具备该角色能力"))

    for assignment in existing_assignments:
        if (
            assignment.actor_id == candidate.actor_id
            and assignment.performance.id == candidate.performance.id
        ):
            violations.append(RuleViolation("actor_already_in_performance", "演员同场已出演其他角色"))
            break

    cap = low_rating_caps.get(candidate.actor_id)
    if cap is not None and monthly_counts.get(candidate.actor_id, 0) >= cap:
        violations.append(RuleViolation("low_rating_cap_reached", "低评级演员本月已达上限"))

    return violations


def would_exceed_consecutive_limit(
    actor_id: int,
    target_slot: PerformanceSlot,
    existing_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: int,
) -> bool:
    actor_slots = sorted(
        [*existing_slots.get(actor_id, []), target_slot],
        key=lambda item: (item.date, SLOT_ORDER[item.slot]),
    )
    longest = 0
    current = 0
    previous: PerformanceSlot | None = None

    for slot in actor_slots:
        if previous is None or _is_next_consecutive(previous, slot):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = slot

    return longest > max_consecutive


def _is_next_consecutive(previous: PerformanceSlot, current: PerformanceSlot) -> bool:
    if previous.date == current.date:
        return previous.slot == "early" and current.slot == "late"
    if (current.date - previous.date).days == 1:
        return previous.slot == "late" and current.slot == "early"
    return False
```

- [ ] **Step 4: Run rule tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_rules.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/scheduling.py backend/app/services/rules.py backend/tests/test_rules.py
git commit -m "feat: enforce core scheduling hard rules"
```

---

### Task 5: Weekly Scheduler

**Files:**
- Modify: `backend/app/schemas/scheduling.py`
- Create: `backend/app/services/scheduler.py`
- Create: `backend/tests/test_scheduler.py`

**Interfaces:**
- Produces `DesignationInput`
- Produces `WishInput`
- Produces `ScheduleResult`
- Produces `generate_week_schedule(...) -> ScheduleResult`

- [ ] **Step 1: Write failing scheduler tests**

Create `backend/tests/test_scheduler.py`:

```python
from datetime import date, datetime

from app.models.enums import DesignationType
from app.schemas.scheduling import DesignationInput, PerformanceSlot, WishInput
from app.services.scheduler import generate_week_schedule


def test_scheduler_satisfies_higher_priority_designation_first():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[
            DesignationInput(DesignationType.PAIRED, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)),
            DesignationInput(DesignationType.UNIVERSAL, "玩家B", 10, 2, performance.id, datetime(2026, 6, 1, 13)),
        ],
        wishes=[],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2
    assert result.unsatisfied_designations[0].actor_id == 1


def test_scheduler_uses_wish_only_after_designations():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[],
        wishes=[WishInput("玩家A", 10, 2, "想看2")],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2


def test_scheduler_explains_unsatisfied_designation_on_leave():
    performance = PerformanceSlot(1, date(2026, 6, 5), "early")

    result = generate_week_schedule(
        performances=[performance],
        role_ids=[10],
        actor_ids=[1, 2],
        actor_role_ids={1: {10}, 2: {10}},
        max_consecutive={1: 3, 2: 3},
        approved_leave_dates={1: {date(2026, 6, 5)}},
        low_rating_caps={},
        monthly_counts={},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[
            DesignationInput(DesignationType.UNIVERSAL, "玩家A", 10, 1, performance.id, datetime(2026, 6, 1, 12)),
        ],
        wishes=[],
    )

    assert result.assignments[(performance.id, 10)].actor_id == 2
    assert result.unsatisfied_designations[0].failure_reason == "演员当天已批准请假"
```

- [ ] **Step 2: Run scheduler tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_scheduler.py -q
```

Expected: FAIL with missing scheduler types/functions.

- [ ] **Step 3: Extend scheduling schemas**

Append to `backend/app/schemas/scheduling.py`:

```python
from datetime import datetime

from app.models.enums import DesignationType


@dataclass(frozen=True)
class DesignationInput:
    designation_type: DesignationType
    player_name: str
    role_id: int
    actor_id: int
    target_performance_id: int | None
    submitted_at: datetime
    failure_reason: str | None = None


@dataclass(frozen=True)
class WishInput:
    player_name: str
    role_id: int
    actor_id: int
    note: str | None = None


@dataclass(frozen=True)
class ScheduleResult:
    assignments: dict[tuple[int, int], AssignmentCandidate]
    unsatisfied_designations: list[DesignationInput]
    unsatisfied_wishes: list[WishInput]
    empty_slots: list[tuple[int, int]]
    explanations: dict[tuple[int, int, int], list[RuleViolation]]
```

- [ ] **Step 4: Implement weekly scheduler**

Create `backend/app/services/scheduler.py`:

```python
from dataclasses import replace
from datetime import date

from app.models.enums import DesignationType
from app.schemas.scheduling import (
    AssignmentCandidate,
    DesignationInput,
    PerformanceSlot,
    RuleViolation,
    ScheduleResult,
    WishInput,
)
from app.services.rules import validate_candidate, would_exceed_consecutive_limit


DESIGNATION_PRIORITY = {
    DesignationType.UNIVERSAL: 0,
    DesignationType.TOP_THREE: 1,
    DesignationType.PAIRED: 2,
}


def generate_week_schedule(
    performances: list[PerformanceSlot],
    role_ids: list[int],
    actor_ids: list[int],
    actor_role_ids: dict[int, set[int]],
    max_consecutive: dict[int, int],
    approved_leave_dates: dict[int, set[date]],
    low_rating_caps: dict[int, int],
    monthly_counts: dict[int, int],
    existing_actor_slots: dict[int, list[PerformanceSlot]],
    locked_assignments: list[AssignmentCandidate],
    designations: list[DesignationInput],
    wishes: list[WishInput],
) -> ScheduleResult:
    assignments: dict[tuple[int, int], AssignmentCandidate] = {}
    explanations: dict[tuple[int, int, int], list[RuleViolation]] = {}
    unsatisfied_designations: list[DesignationInput] = []
    mutable_monthly_counts = dict(monthly_counts)
    mutable_actor_slots = {actor_id: list(slots) for actor_id, slots in existing_actor_slots.items()}

    for assignment in locked_assignments:
        assignments[(assignment.performance.id, assignment.role_id)] = assignment
        mutable_monthly_counts[assignment.actor_id] = mutable_monthly_counts.get(assignment.actor_id, 0) + 1
        mutable_actor_slots.setdefault(assignment.actor_id, []).append(assignment.performance)

    sorted_designations = sorted(
        designations,
        key=lambda item: (DESIGNATION_PRIORITY[item.designation_type], item.submitted_at),
    )
    performance_by_id = {performance.id: performance for performance in performances}

    for designation in sorted_designations:
        target_performances = (
            [performance_by_id[designation.target_performance_id]]
            if designation.target_performance_id in performance_by_id
            else performances
        )
        placed = False
        last_reason = "没有可用场次"
        for performance in target_performances:
            key = (performance.id, designation.role_id)
            if key in assignments:
                last_reason = "目标槽位已被更高优先级记录占用"
                continue
            candidate = AssignmentCandidate(designation.actor_id, designation.role_id, performance)
            violations = _violations_for_candidate(
                candidate,
                assignments,
                approved_leave_dates,
                actor_role_ids,
                mutable_monthly_counts,
                low_rating_caps,
                mutable_actor_slots,
                max_consecutive,
            )
            explanations[(performance.id, designation.role_id, designation.actor_id)] = violations
            if violations:
                last_reason = violations[0].message
                continue
            _place(candidate, assignments, mutable_monthly_counts, mutable_actor_slots)
            placed = True
            break
        if not placed:
            unsatisfied_designations.append(replace(designation, failure_reason=last_reason))

    for performance in performances:
        for role_id in role_ids:
            key = (performance.id, role_id)
            if key in assignments:
                continue
            best_candidate = _best_candidate(
                performance,
                role_id,
                actor_ids,
                actor_role_ids,
                approved_leave_dates,
                low_rating_caps,
                mutable_monthly_counts,
                mutable_actor_slots,
                max_consecutive,
                assignments,
                wishes,
            )
            if best_candidate is not None:
                _place(best_candidate, assignments, mutable_monthly_counts, mutable_actor_slots)

    empty_slots = [
        (performance.id, role_id)
        for performance in performances
        for role_id in role_ids
        if (performance.id, role_id) not in assignments
    ]
    unsatisfied_wishes = [
        wish
        for wish in wishes
        if not any(
            assignment.role_id == wish.role_id and assignment.actor_id == wish.actor_id
            for assignment in assignments.values()
        )
    ]

    return ScheduleResult(assignments, unsatisfied_designations, unsatisfied_wishes, empty_slots, explanations)


def _best_candidate(
    performance: PerformanceSlot,
    role_id: int,
    actor_ids: list[int],
    actor_role_ids: dict[int, set[int]],
    approved_leave_dates: dict[int, set[date]],
    low_rating_caps: dict[int, int],
    monthly_counts: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: dict[int, int],
    assignments: dict[tuple[int, int], AssignmentCandidate],
    wishes: list[WishInput],
) -> AssignmentCandidate | None:
    valid: list[tuple[int, AssignmentCandidate]] = []
    for actor_id in actor_ids:
        candidate = AssignmentCandidate(actor_id, role_id, performance)
        violations = _violations_for_candidate(
            candidate,
            assignments,
            approved_leave_dates,
            actor_role_ids,
            monthly_counts,
            low_rating_caps,
            actor_slots,
            max_consecutive,
        )
        if violations:
            continue
        wish_score = 100 if any(wish.role_id == role_id and wish.actor_id == actor_id for wish in wishes) else 0
        balance_score = -monthly_counts.get(actor_id, 0)
        valid.append((wish_score + balance_score, candidate))
    if not valid:
        return None
    return sorted(valid, key=lambda item: (-item[0], item[1].actor_id))[0][1]


def _violations_for_candidate(
    candidate: AssignmentCandidate,
    assignments: dict[tuple[int, int], AssignmentCandidate],
    approved_leave_dates: dict[int, set[date]],
    actor_role_ids: dict[int, set[int]],
    monthly_counts: dict[int, int],
    low_rating_caps: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
    max_consecutive: dict[int, int],
) -> list[RuleViolation]:
    violations = validate_candidate(
        candidate,
        list(assignments.values()),
        approved_leave_dates,
        actor_role_ids,
        monthly_counts,
        low_rating_caps,
    )
    if would_exceed_consecutive_limit(
        candidate.actor_id,
        candidate.performance,
        actor_slots,
        max_consecutive.get(candidate.actor_id, 3),
    ):
        violations.append(RuleViolation("consecutive_limit_exceeded", "超过演员个人最大连场数"))
    return violations


def _place(
    candidate: AssignmentCandidate,
    assignments: dict[tuple[int, int], AssignmentCandidate],
    monthly_counts: dict[int, int],
    actor_slots: dict[int, list[PerformanceSlot]],
) -> None:
    assignments[(candidate.performance.id, candidate.role_id)] = candidate
    monthly_counts[candidate.actor_id] = monthly_counts.get(candidate.actor_id, 0) + 1
    actor_slots.setdefault(candidate.actor_id, []).append(candidate.performance)
```

- [ ] **Step 5: Run scheduler tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_scheduler.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/scheduling.py backend/app/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat: generate weekly schedules with priority explanations"
```

---

### Task 6: Group Text Import Parser

**Files:**
- Create: `backend/app/schemas/imports.py`
- Create: `backend/app/services/import_parser.py`
- Create: `backend/tests/test_import_parser.py`

**Interfaces:**
- Produces `ImportDraft`
- Produces `parse_group_board(text: str) -> ImportDraft`

- [ ] **Step 1: Write failing parser tests**

Create `backend/tests/test_import_parser.py`:

```python
from app.services.import_parser import parse_group_board


def test_parse_group_board_extracts_wishes_players_and_notes():
    text = """
#指定信息⬇️
【虔诚许愿】-小展/长离-Jennifer 山风昭昭可以原地转十个圈
热力榜三-文轩/轩辕重光（四月热力榜-兹）
#玩家信息⬇️
女位：
【昭昭】长离（恋）： Jennifer-14-3
【观禾】轩辕重光（恋）：嘻嘻
#场内点心⬇️
昭昭：
放房间：两瓶水，蓝莓
#其他备注⬇️
观禾：开观禾2.0
"""

    draft = parse_group_board(text)

    assert draft.wishes[0].actor_name == "小展"
    assert draft.wishes[0].role_name == "长离"
    assert draft.wishes[0].player_name == "Jennifer"
    assert draft.designation_suggestions[0].suggested_type == "top_three"
    assert draft.players[0].label == "昭昭"
    assert draft.players[0].role_name == "长离"
    assert draft.notes["昭昭"] == "放房间：两瓶水，蓝莓"
    assert draft.notes["观禾"] == "开观禾2.0"
```

- [ ] **Step 2: Run parser test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_import_parser.py -q
```

Expected: FAIL with missing parser.

- [ ] **Step 3: Implement import schemas**

Create `backend/app/schemas/imports.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WishDraft:
    actor_name: str
    role_name: str
    player_name: str
    raw_note: str


@dataclass(frozen=True)
class DesignationSuggestion:
    actor_name: str
    role_name: str
    player_name: str | None
    suggested_type: str
    raw_line: str


@dataclass(frozen=True)
class PlayerDraft:
    label: str
    role_name: str
    relation: str | None
    player_name: str


@dataclass(frozen=True)
class ImportDraft:
    wishes: list[WishDraft] = field(default_factory=list)
    designation_suggestions: list[DesignationSuggestion] = field(default_factory=list)
    players: list[PlayerDraft] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    unresolved_lines: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Implement group board parser**

Create `backend/app/services/import_parser.py`:

```python
import re

from app.schemas.imports import DesignationSuggestion, ImportDraft, PlayerDraft, WishDraft


SECTION_MARKERS = {
    "#指定信息": "designations",
    "#玩家信息": "players",
    "#场内点心": "snacks",
    "#其他备注": "other_notes",
}


def parse_group_board(text: str) -> ImportDraft:
    sections: dict[str, list[str]] = {name: [] for name in SECTION_MARKERS.values()}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker = next((value for key, value in SECTION_MARKERS.items() if line.startswith(key)), None)
        if marker:
            current = marker
            continue
        if current:
            sections[current].append(line)

    wishes: list[WishDraft] = []
    suggestions: list[DesignationSuggestion] = []
    unresolved: list[str] = []
    for line in sections["designations"]:
        if "虔诚许愿" in line:
            wish = _parse_wish(line)
            wishes.append(wish) if wish else unresolved.append(line)
        elif "热力榜三" in line:
            suggestion = _parse_top_three(line)
            suggestions.append(suggestion) if suggestion else unresolved.append(line)
        else:
            unresolved.append(line)

    players: list[PlayerDraft] = []
    for line in sections["players"]:
        parsed = _parse_player(line)
        if parsed:
            players.append(parsed)

    notes = _parse_notes(sections["snacks"]) | _parse_notes(sections["other_notes"])
    return ImportDraft(wishes, suggestions, players, notes, unresolved)


def _parse_wish(line: str) -> WishDraft | None:
    match = re.search(r"】-?\s*([^/]+)/([^-（(]+)-([^（(]+)(.*)$", line)
    if not match:
        return None
    return WishDraft(
        actor_name=match.group(1).strip(),
        role_name=match.group(2).strip(),
        player_name=match.group(3).strip(),
        raw_note=match.group(4).strip(" ()（）"),
    )


def _parse_top_three(line: str) -> DesignationSuggestion | None:
    match = re.search(r"热力榜三-([^/]+)/([^（(]+)", line)
    if not match:
        return None
    return DesignationSuggestion(
        actor_name=match.group(1).strip(),
        role_name=match.group(2).strip(),
        player_name=None,
        suggested_type="top_three",
        raw_line=line,
    )


def _parse_player(line: str) -> PlayerDraft | None:
    match = re.search(r"【([^】]+)】([^（(：:]+)(?:[（(]([^）)]+)[）)])?[：:]\s*(.+)$", line)
    if not match:
        return None
    return PlayerDraft(
        label=match.group(1).strip(),
        role_name=match.group(2).strip(),
        relation=match.group(3).strip() if match.group(3) else None,
        player_name=match.group(4).strip(),
    )


def _parse_notes(lines: list[str]) -> dict[str, str]:
    notes: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []
    for line in lines:
        if line.endswith("：") or line.endswith(":"):
            if current_key and buffer:
                notes[current_key] = " ".join(buffer).strip()
            current_key = line.rstrip("：:")
            buffer = []
        elif "：" in line or ":" in line:
            key, value = re.split(r"[：:]", line, maxsplit=1)
            if current_key and buffer:
                notes[current_key] = " ".join(buffer).strip()
            current_key = key.strip()
            buffer = [value.strip()]
        elif current_key:
            buffer.append(line)
    if current_key and buffer:
        notes[current_key] = " ".join(buffer).strip()
    return notes
```

- [ ] **Step 5: Run parser test and verify it passes**

Run:

```bash
cd backend && pytest tests/test_import_parser.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/imports.py backend/app/services/import_parser.py backend/tests/test_import_parser.py
git commit -m "feat: parse group board drafts"
```

---

### Task 7: Auth and Core API Routes

**Files:**
- Create: `backend/app/services/auth.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/routes/auth.py`
- Create: `backend/app/api/routes/admin.py`
- Create: `backend/app/api/routes/actor.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api_smoke.py`

**Interfaces:**
- Produces `POST /auth/login`
- Produces `GET /admin/dashboard`
- Produces `GET /actor/me/schedule`
- Produces `POST /actor/me/leave-requests`

- [ ] **Step 1: Extend API smoke tests**

Append to `backend/tests/test_api_smoke.py`:

```python

def test_admin_dashboard_requires_auth():
    client = TestClient(app)
    response = client.get("/admin/dashboard")
    assert response.status_code == 401


def test_actor_schedule_requires_auth():
    client = TestClient(app)
    response = client.get("/actor/me/schedule")
    assert response.status_code == 401
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
cd backend && pytest tests/test_api_smoke.py -q
```

Expected: FAIL because routes do not exist or do not return 401.

- [ ] **Step 3: Implement minimal auth dependencies**

Create `backend/app/schemas/auth.py`:

```python
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

Create `backend/app/services/auth.py`:

```python
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings


def create_access_token(subject: str, role: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": subject, "role": role, "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
```

Create `backend/app/api/deps.py`:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings


bearer = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    return {"sub": str(payload["sub"]), "role": str(payload["role"])}


def require_admin(user: dict[str, str] = Depends(require_user)) -> dict[str, str]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
```

- [ ] **Step 4: Implement routes**

Create `backend/app/api/routes/auth.py`:

```python
from fastapi import APIRouter, HTTPException

from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if payload.email == "admin@example.com" and payload.password == "admin":
        return TokenResponse(access_token=create_access_token(payload.email, "admin"))
    if payload.email == "actor@example.com" and payload.password == "actor":
        return TokenResponse(access_token=create_access_token(payload.email, "actor"))
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

Create `backend/app/api/routes/admin.py`:

```python
from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def dashboard(_: dict[str, str] = Depends(require_admin)) -> dict[str, int]:
    return {
        "pending_leave_requests": 0,
        "pending_designations": 0,
        "approval_required_assignments": 0,
        "unpublished_performances": 0,
    }
```

Create `backend/app/api/routes/actor.py`:

```python
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_user

router = APIRouter(prefix="/actor", tags=["actor"])


class LeaveRequestInput(BaseModel):
    dates: list[date]
    note: str | None = None


@router.get("/me/schedule")
def my_schedule(_: dict[str, str] = Depends(require_user)) -> list[dict[str, str]]:
    return []


@router.post("/me/leave-requests")
def submit_leave(payload: LeaveRequestInput, _: dict[str, str] = Depends(require_user)) -> dict[str, object]:
    return {"status": "submitted", "dates": [item.isoformat() for item in payload.dates]}
```

Modify `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.api.routes import actor, admin, auth
from app.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(actor.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run API tests and verify they pass**

Run:

```bash
cd backend && pytest tests/test_api_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_api_smoke.py
git commit -m "feat: add auth and role-gated api routes"
```

---

### Task 8: Scheduling API Integration

**Files:**
- Create: `backend/app/api/routes/scheduling.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_scheduling_api.py`

**Interfaces:**
- Produces `POST /scheduling/preview`
- Consumes `generate_week_schedule`

- [ ] **Step 1: Write failing scheduling API test**

Create `backend/tests/test_scheduling_api.py`:

```python
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
```

- [ ] **Step 2: Run scheduling API test and verify it fails**

Run:

```bash
cd backend && pytest tests/test_scheduling_api.py -q
```

Expected: FAIL with missing `/scheduling/preview`.

- [ ] **Step 3: Implement scheduling preview route**

Create `backend/app/api/routes/scheduling.py`:

```python
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_admin
from app.models.enums import DesignationType
from app.schemas.scheduling import DesignationInput, PerformanceSlot, WishInput
from app.services.scheduler import generate_week_schedule

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


class PerformancePayload(BaseModel):
    id: int
    date: date
    slot: str


class DesignationPayload(BaseModel):
    designation_type: DesignationType
    player_name: str
    role_id: int
    actor_id: int
    target_performance_id: int | None = None
    submitted_at: datetime


class WishPayload(BaseModel):
    player_name: str
    role_id: int
    actor_id: int
    note: str | None = None


class SchedulingPreviewRequest(BaseModel):
    performances: list[PerformancePayload]
    role_ids: list[int]
    actor_ids: list[int]
    actor_role_ids: dict[str, list[int]]
    max_consecutive: dict[str, int]
    approved_leave_dates: dict[str, list[date]]
    low_rating_caps: dict[str, int]
    monthly_counts: dict[str, int]
    designations: list[DesignationPayload]
    wishes: list[WishPayload]


@router.post("/preview")
def preview_schedule(payload: SchedulingPreviewRequest, _: dict[str, str] = Depends(require_admin)) -> dict[str, object]:
    result = generate_week_schedule(
        performances=[PerformanceSlot(item.id, item.date, item.slot) for item in payload.performances],
        role_ids=payload.role_ids,
        actor_ids=payload.actor_ids,
        actor_role_ids={int(key): set(value) for key, value in payload.actor_role_ids.items()},
        max_consecutive={int(key): value for key, value in payload.max_consecutive.items()},
        approved_leave_dates={int(key): set(value) for key, value in payload.approved_leave_dates.items()},
        low_rating_caps={int(key): value for key, value in payload.low_rating_caps.items()},
        monthly_counts={int(key): value for key, value in payload.monthly_counts.items()},
        existing_actor_slots={},
        locked_assignments=[],
        designations=[
            DesignationInput(
                item.designation_type,
                item.player_name,
                item.role_id,
                item.actor_id,
                item.target_performance_id,
                item.submitted_at,
            )
            for item in payload.designations
        ],
        wishes=[WishInput(item.player_name, item.role_id, item.actor_id, item.note) for item in payload.wishes],
    )
    return {
        "assignments": [
            {"performance_id": performance_id, "role_id": role_id, "actor_id": assignment.actor_id}
            for (performance_id, role_id), assignment in sorted(result.assignments.items())
        ],
        "unsatisfied_designations": [
            {
                "player_name": item.player_name,
                "role_id": item.role_id,
                "actor_id": item.actor_id,
                "failure_reason": item.failure_reason,
            }
            for item in result.unsatisfied_designations
        ],
        "empty_slots": [{"performance_id": item[0], "role_id": item[1]} for item in result.empty_slots],
    }
```

Modify `backend/app/main.py` to include the router:

```python
from app.api.routes import actor, admin, auth, scheduling

app.include_router(scheduling.router)
```

- [ ] **Step 4: Run scheduling API test and verify it passes**

Run:

```bash
cd backend && pytest tests/test_scheduling_api.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/scheduling.py backend/app/main.py backend/tests/test_scheduling_api.py
git commit -m "feat: expose scheduling preview api"
```

---

### Task 9: Frontend Shell, Auth, and Navigation

**Files:**
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/auth/AuthContext.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/tests/scheduling-ui.test.tsx`

**Interfaces:**
- Produces `ApiClient`
- Produces `AuthProvider`
- Produces role-aware navigation

- [ ] **Step 1: Write failing frontend test**

Create `frontend/tests/scheduling-ui.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "../src/App";

test("renders login screen by default", () => {
  render(<App />);
  expect(screen.getByText("剧场卡司排班")).toBeInTheDocument();
  expect(screen.getByLabelText("邮箱")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run frontend test and verify it fails**

Run:

```bash
cd frontend && npm run test
```

Expected: FAIL because test environment or login screen is missing.

- [ ] **Step 3: Add frontend config**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "tests"]
}
```

Create `frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

Create `frontend/src/styles.css`:

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f7f8fa;
  color: #1f2933;
}

button,
input,
select,
textarea {
  font: inherit;
}

.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.panel {
  width: min(420px, 100%);
  background: #ffffff;
  border: 1px solid #d9dee7;
  border-radius: 8px;
  padding: 24px;
}

.field {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
}

.button {
  border: 0;
  border-radius: 6px;
  background: #1f6feb;
  color: white;
  padding: 10px 14px;
  cursor: pointer;
}

.shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
}

.sidebar {
  background: #111827;
  color: white;
  padding: 20px;
}

.nav {
  display: grid;
  gap: 8px;
}

.content {
  padding: 24px;
}
```

- [ ] **Step 4: Implement auth shell**

Create `frontend/src/api/client.ts`:

```ts
export class ApiClient {
  constructor(private readonly baseUrl = "http://localhost:8000") {}

  async login(email: string, password: string): Promise<{ access_token: string }> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error("登录失败");
    return response.json();
  }
}

export const apiClient = new ApiClient();
```

Create `frontend/src/auth/AuthContext.tsx`:

```tsx
import React, { createContext, useContext, useMemo, useState } from "react";

type Role = "admin" | "actor";

type AuthState = {
  token: string | null;
  role: Role | null;
  setSession: (token: string, role: Role) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);

  const value = useMemo<AuthState>(
    () => ({
      token,
      role,
      setSession(nextToken, nextRole) {
        setToken(nextToken);
        setRole(nextRole);
      },
      logout() {
        setToken(null);
        setRole(null);
      },
    }),
    [token, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
```

Create `frontend/src/pages/LoginPage.tsx`:

```tsx
import { useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { setSession } = useAuth();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const response = await apiClient.login(email, password);
    setSession(response.access_token, email.startsWith("actor") ? "actor" : "admin");
  }

  return (
    <main className="login">
      <form className="panel" onSubmit={submit}>
        <h1>剧场卡司排班</h1>
        <label className="field">
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field">
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button className="button" type="submit">登录</button>
      </form>
    </main>
  );
}
```

Create `frontend/src/components/AppShell.tsx`:

```tsx
import { CalendarDays, ClipboardList, Home, UserRound } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export function AppShell() {
  const { role, logout } = useAuth();
  const adminItems = [
    ["工作台", Home],
    ["月度计划", CalendarDays],
    ["请假审核", ClipboardList],
    ["周排班", ClipboardList],
  ] as const;
  const actorItems = [
    ["我的排班", CalendarDays],
    ["我的请假", UserRound],
  ] as const;
  const items = role === "admin" ? adminItems : actorItems;

  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>剧场卡司排班</h1>
        <nav className="nav">
          {items.map(([label, Icon]) => (
            <button className="button" key={label} type="button">
              <Icon size={16} /> {label}
            </button>
          ))}
          <button className="button" type="button" onClick={logout}>退出</button>
        </nav>
      </aside>
      <main className="content">请选择一个工作区</main>
    </div>
  );
}
```

Modify `frontend/src/App.tsx`:

```tsx
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import "./styles.css";

function AppContent() {
  const { token } = useAuth();
  return token ? <AppShell /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
```

- [ ] **Step 5: Run frontend test and verify it passes**

Run:

```bash
cd frontend && npm run test
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: add frontend auth shell"
```

---

### Task 10: Admin and Actor Workflow Screens

**Files:**
- Create: `frontend/src/pages/admin/DashboardPage.tsx`
- Create: `frontend/src/pages/admin/MonthlyPlanPage.tsx`
- Create: `frontend/src/pages/admin/RequestsPage.tsx`
- Create: `frontend/src/pages/admin/WeeklySchedulingPage.tsx`
- Create: `frontend/src/pages/actor/MySchedulePage.tsx`
- Create: `frontend/src/pages/actor/MyLeavePage.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/tests/scheduling-ui.test.tsx`

**Interfaces:**
- Produces visible admin pages for dashboard, monthly plan, requests, weekly scheduling
- Produces visible actor pages for schedule and leave

- [ ] **Step 1: Add failing navigation test**

Append to `frontend/tests/scheduling-ui.test.tsx`:

```tsx
import { fireEvent, waitFor } from "@testing-library/react";

test("admin can see weekly scheduling navigation after login", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "token" }), { status: 200 })));
  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("周排班")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run frontend tests and verify new test passes or exposes missing import**

Run:

```bash
cd frontend && npm run test
```

Expected: if imports are missing, FAIL with TypeScript or runtime errors.

- [ ] **Step 3: Implement workflow pages**

Create `frontend/src/pages/admin/DashboardPage.tsx`:

```tsx
export function DashboardPage() {
  return <section><h2>工作台</h2><p>待处理请假、指定、审批和未发布场次会在这里汇总。</p></section>;
}
```

Create `frontend/src/pages/admin/MonthlyPlanPage.tsx`:

```tsx
export function MonthlyPlanPage() {
  return <section><h2>月度计划</h2><p>生成整月场次、标记公休、审核请假、设置演员评级。</p></section>;
}
```

Create `frontend/src/pages/admin/RequestsPage.tsx`:

```tsx
export function RequestsPage() {
  return <section><h2>请假审核</h2><p>批量批准或拒绝演员提交的整天请假。</p></section>;
}
```

Create `frontend/src/pages/admin/WeeklySchedulingPage.tsx`:

```tsx
export function WeeklySchedulingPage() {
  return (
    <section>
      <h2>周排班</h2>
      <p>锁定关键卡司，生成补排，查看指定失败和硬规则冲突。</p>
      <div className="panel">排班表区域</div>
    </section>
  );
}
```

Create `frontend/src/pages/actor/MySchedulePage.tsx`:

```tsx
export function MySchedulePage() {
  return <section><h2>我的排班</h2><p>查看已发布班次和管理员允许展示的草稿班次。</p></section>;
}
```

Create `frontend/src/pages/actor/MyLeavePage.tsx`:

```tsx
export function MyLeavePage() {
  return <section><h2>我的请假</h2><p>按月提交整天请假，查看审核状态。</p></section>;
}
```

Modify `frontend/src/components/AppShell.tsx` to hold selected page:

```tsx
import { CalendarDays, ClipboardList, Home, UserRound } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { DashboardPage } from "../pages/admin/DashboardPage";
import { MonthlyPlanPage } from "../pages/admin/MonthlyPlanPage";
import { RequestsPage } from "../pages/admin/RequestsPage";
import { WeeklySchedulingPage } from "../pages/admin/WeeklySchedulingPage";
import { MyLeavePage } from "../pages/actor/MyLeavePage";
import { MySchedulePage } from "../pages/actor/MySchedulePage";

export function AppShell() {
  const { role, logout } = useAuth();
  const [page, setPage] = useState("工作台");
  const adminItems = [
    ["工作台", Home],
    ["月度计划", CalendarDays],
    ["请假审核", ClipboardList],
    ["周排班", ClipboardList],
  ] as const;
  const actorItems = [
    ["我的排班", CalendarDays],
    ["我的请假", UserRound],
  ] as const;
  const items = role === "admin" ? adminItems : actorItems;

  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>剧场卡司排班</h1>
        <nav className="nav">
          {items.map(([label, Icon]) => (
            <button className="button" key={label} type="button" onClick={() => setPage(label)}>
              <Icon size={16} /> {label}
            </button>
          ))}
          <button className="button" type="button" onClick={logout}>退出</button>
        </nav>
      </aside>
      <main className="content">{renderPage(page)}</main>
    </div>
  );
}

function renderPage(page: string) {
  if (page === "工作台") return <DashboardPage />;
  if (page === "月度计划") return <MonthlyPlanPage />;
  if (page === "请假审核") return <RequestsPage />;
  if (page === "周排班") return <WeeklySchedulingPage />;
  if (page === "我的请假") return <MyLeavePage />;
  return <MySchedulePage />;
}
```

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
cd frontend && npm run test && npm run build
```

Expected: tests and build pass.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add admin and actor workflow screens"
```

---

### Task 11: End-to-End Verification and Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/acceptance-checklist.md`

**Interfaces:**
- Produces documented local run commands
- Produces acceptance checklist matching the approved spec

- [ ] **Step 1: Run all backend tests**

Run:

```bash
cd backend && pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run all frontend tests and build**

Run:

```bash
cd frontend && npm run test && npm run build
```

Expected: all frontend tests pass and production build succeeds.

- [ ] **Step 3: Create acceptance checklist**

Create `docs/superpowers/acceptance-checklist.md`:

```markdown
# 剧场卡司排班 V1 验收清单

- [ ] 管理员可以登录。
- [ ] 演员可以登录。
- [ ] 系统可以生成月度场次草稿，支持每周不同早晚场模板。
- [ ] 公休日期不会生成可排场次。
- [ ] 演员整天请假会阻止当天所有排班。
- [ ] 演员可出演多个角色，但同一场不能出演两个角色。
- [ ] 默认 3 连、个人 2 连、个人 1 连限制可测试。
- [ ] 指定优先级为万能指定 > 榜单前三指定 > 对位指定。
- [ ] 指定失败会显示原因。
- [ ] 许愿只影响补排，不压过指定。
- [ ] 低评级月度上限会阻止发布或触发审批。
- [ ] 群统计文本导入生成草稿确认数据，不直接写正式记录。
- [ ] 演员可以提交整天请假。
- [ ] 管理员可以看到周排班和待处理队列。
```

- [ ] **Step 4: Update README with verification commands**

Replace `README.md` with:

```markdown
# 剧场卡司排班

V1 theater cast scheduling system for monthly capacity planning and weekly semi-automatic cast scheduling.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn app.main:app --reload
```

Backend health check: http://localhost:8000/health

## Frontend

```bash
cd frontend
npm install
npm run test
npm run dev
```

Frontend dev server: http://localhost:5173

## Demo Accounts

- Admin: `admin@example.com` / `admin`
- Actor: `actor@example.com` / `actor`

## Design and Plan

- Design: `docs/superpowers/specs/2026-07-12-theater-cast-scheduling-design.md`
- Plan: `docs/superpowers/plans/2026-07-12-theater-cast-scheduling.md`
- Acceptance checklist: `docs/superpowers/acceptance-checklist.md`
```

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/acceptance-checklist.md
git commit -m "docs: add v1 acceptance checklist"
```

---

## Self-Review

Spec coverage:

- Admin and actor roles are covered by Tasks 7, 9, and 10.
- Monthly capacity and public holiday generation are covered by Task 3.
- Fixed roles and cross-cast actor capabilities are covered by Task 2.
- Full-day leave is covered by Tasks 2, 4, 7, and 10.
- Hard rules, max consecutive performances, and low-rating caps are covered by Tasks 4 and 5.
- Designation priority and wish priority are covered by Task 5.
- Group text import confirmation drafts are covered by Task 6.
- Scheduling API is covered by Task 8.
- Admin and actor UI entry points are covered by Tasks 9 and 10.
- Verification and acceptance checklist are covered by Task 11.

Known implementation boundary:

- This plan builds a functional V1 skeleton and tested scheduling core. It does not yet implement every persistent CRUD screen for theaters, roles, actors, designations, wishes, and monthly plans. Those should be added in a follow-up CRUD expansion plan after the scheduling core, auth shell, and workflow pages are running.
