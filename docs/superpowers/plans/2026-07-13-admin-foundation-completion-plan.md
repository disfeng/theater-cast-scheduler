# Admin Foundation Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the V1 admin data-entry workflows and make monthly-plan regeneration safe for existing scheduling data.

**Architecture:** Keep FastAPI routes as adapters over focused SQLAlchemy services, using Pydantic for template validation and a domain conflict exception for safe regeneration. Keep React pages local and explicit: each page owns its form state, calls typed `ApiClient` methods, refreshes server data after mutations, and renders actionable errors.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest, TypeScript, React, Vitest, Testing Library, Vite.

## Global Constraints

- Work directly on `main`, as explicitly requested for V1.
- Use test-driven development: add one failing behavior test before each implementation increment.
- Weekly template keys are only `monday` through `sunday`; slots are only `early` and `late`; duplicate slots are invalid.
- Regeneration may replace only unreferenced draft performances. Non-draft or referenced performances produce HTTP 409 without data changes.
- Frontend forms use inline controls and lists; do not add dialogs, a generic CRUD framework, or a wizard.
- Keep generated files out of Git.

---

## File Structure

Modify these files:

```text
backend/app/schemas/admin.py                     weekly-template validation
backend/app/services/admin_data.py               atomic capability replacement
backend/app/services/monthly_plan.py             safe regeneration and domain conflict
backend/app/api/routes/admin.py                   409 translation and rollback boundary
backend/tests/test_admin_api.py                   validation and capability atomicity
backend/tests/test_monthly_plan_api.py            regeneration safety
frontend/src/api/client.ts                       update/capability methods and API errors
frontend/src/pages/admin/SettingsPage.tsx        theater and role entry
frontend/src/pages/admin/ActorsPage.tsx          actor entry and editing
frontend/src/pages/admin/MonthlyPlanPage.tsx      generation controls
frontend/tests/admin-workflows.test.tsx           mutation workflow coverage
docs/superpowers/acceptance-checklist.md          verified acceptance status
```

---

### Task 1: Backend Validation and Atomic Capability Replacement

**Files:**
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/admin_data.py`
- Modify: `backend/tests/test_admin_api.py`

**Interfaces:**
- Produces validated `TheaterCreate.default_weekly_template: dict[str, list[Literal["early", "late"]]]`.
- Preserves `replace_actor_capabilities(db, actor_id, role_ids) -> Actor` while making invalid-role failures non-mutating.

- [ ] **Step 1: Add failing validation and atomicity tests**

Append to `backend/tests/test_admin_api.py`:

```python
import pytest
from pydantic import ValidationError


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
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd backend && pytest tests/test_admin_api.py::test_theater_template_rejects_invalid_keys_slots_and_duplicates tests/test_admin_api.py::test_invalid_capability_replacement_preserves_existing_roles -q
```

Expected: validation cases do not raise and the atomicity test loses the original capability.

- [ ] **Step 3: Implement weekly-template validation**

In `backend/app/schemas/admin.py`, add imports and a field validator:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
Slot = Literal["early", "late"]


class TheaterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    default_weekly_template: dict[Weekday, list[Slot]]

    @field_validator("default_weekly_template")
    @classmethod
    def reject_duplicate_slots(cls, template: dict[Weekday, list[Slot]]):
        if any(len(slots) != len(set(slots)) for slots in template.values()):
            raise ValueError("weekly_template_has_duplicate_slots")
        return template
```

- [ ] **Step 4: Validate all roles before mutation**

Change `replace_actor_capabilities` in `backend/app/services/admin_data.py` so lookup precedes deletion:

```python
def replace_actor_capabilities(db: Session, actor_id: int, role_ids: list[int]) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise LookupError("actor_not_found")
    unique_role_ids = sorted(set(role_ids))
    if any(db.get(Role, role_id) is None for role_id in unique_role_ids):
        raise LookupError("role_not_found")
    for capability in list(actor.role_capabilities):
        db.delete(capability)
    db.flush()
    for role_id in unique_role_ids:
        db.add(ActorRoleCapability(actor_id=actor_id, role_id=role_id))
    db.commit()
    db.refresh(actor)
    return actor
```

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

Run: `cd backend && pytest tests/test_admin_api.py -q`

Expected: all admin tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/services/admin_data.py backend/tests/test_admin_api.py
git commit -m "fix: validate admin templates and capability updates"
```

---

### Task 2: Safe Monthly Regeneration

**Files:**
- Modify: `backend/app/services/monthly_plan.py`
- Modify: `backend/app/api/routes/admin.py`
- Modify: `backend/tests/test_monthly_plan_api.py`

**Interfaces:**
- Produces `MonthlyPlanConflict(Exception)` with stable messages.
- `generate_monthly_plan(...)` raises `MonthlyPlanConflict` for non-draft or referenced performances.
- `POST /admin/monthly-plan/generate` translates this conflict to HTTP 409.

- [ ] **Step 1: Add failing conflict tests**

Append imports and tests to `backend/tests/test_monthly_plan_api.py`:

```python
from datetime import date

from app.models.entities import Performance, Role, ScheduleAssignment
from app.models.enums import PerformanceStatus


def _admin_headers():
    token = create_access_token("admin@example.com", "admin")
    return {"Authorization": f"Bearer {token}"}


def test_monthly_regeneration_rejects_non_draft_performances(db_session):
    theater = create_theater(db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}))
    performance = Performance(theater_id=theater.id, performance_date=date(2026, 6, 1), slot="early", status=PerformanceStatus.PUBLISHED)
    db_session.add(performance)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: iter([db_session])
    try:
        response = TestClient(app).post("/admin/monthly-plan/generate", headers=_admin_headers(), json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []})
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id).status == PerformanceStatus.PUBLISHED
    finally:
        app.dependency_overrides.clear()


def test_monthly_regeneration_rejects_referenced_draft(db_session):
    theater = create_theater(db_session, TheaterCreate(name="西幽剧场", default_weekly_template={"monday": ["early"]}))
    role = Role(name="长离")
    actor = create_actor(db_session, ActorCreate(display_name="小展"))
    performance = Performance(theater_id=theater.id, performance_date=date(2026, 6, 1), slot="early")
    db_session.add_all([role, performance])
    db_session.flush()
    db_session.add(ScheduleAssignment(performance_id=performance.id, role_id=role.id, actor_id=actor.id))
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: iter([db_session])
    try:
        response = TestClient(app).post("/admin/monthly-plan/generate", headers=_admin_headers(), json={"theater_id": theater.id, "year": 2026, "month": 6, "closed_dates": []})
        assert response.status_code == 409
        assert db_session.get(Performance, performance.id) is not None
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the conflict tests and verify RED**

Run: `cd backend && pytest tests/test_monthly_plan_api.py -q`

Expected: one or both new tests fail because existing performances are deleted or an integrity error escapes.

- [ ] **Step 3: Implement conflict detection and rollback**

In `backend/app/services/monthly_plan.py`, import `Designation` and `ScheduleAssignment`, define the exception, and check before deletion:

```python
class MonthlyPlanConflict(Exception):
    pass


def _ensure_regeneration_is_safe(db: Session, existing: list[Performance]) -> None:
    if any(item.status != PerformanceStatus.DRAFT for item in existing):
        raise MonthlyPlanConflict("monthly_plan_has_non_draft_performances")
    performance_ids = [item.id for item in existing]
    if not performance_ids:
        return
    has_assignment = db.scalar(select(ScheduleAssignment.id).where(ScheduleAssignment.performance_id.in_(performance_ids)).limit(1))
    has_designation = db.scalar(select(Designation.id).where(Designation.target_performance_id.in_(performance_ids)).limit(1))
    if has_assignment is not None or has_designation is not None:
        raise MonthlyPlanConflict("monthly_plan_has_referenced_performances")
```

Call `_ensure_regeneration_is_safe(db, list(existing))` before deleting. Wrap the write/commit portion in `try/except Exception: db.rollback(); raise` so failed commits leave a usable session.

- [ ] **Step 4: Translate conflicts to HTTP 409**

Import `MonthlyPlanConflict` in `backend/app/api/routes/admin.py` and add the handler before `LookupError`:

```python
    except MonthlyPlanConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 5: Run backend monthly and admin tests**

Run: `cd backend && pytest tests/test_monthly_plan_api.py tests/test_admin_api.py -q`

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monthly_plan.py backend/app/api/routes/admin.py backend/tests/test_monthly_plan_api.py
git commit -m "fix: protect existing monthly schedules"
```

---

### Task 3: Theater and Role Entry UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/admin/SettingsPage.tsx`
- Modify: `frontend/tests/admin-workflows.test.tsx`

**Interfaces:**
- Preserves `createTheater` and `createRole` methods.
- Produces visible `role="alert"` error messages for failed saves.

- [ ] **Step 1: Add a failing settings mutation test**

Add a Vitest test that records request method/body, opens 基础配置, fills `剧场名称`, checks `周一早场`, submits `保存剧场`, fills `角色名称` and `角色分组`, submits `保存角色`, and asserts POST bodies equal:

```ts
expect(requests).toContainEqual({ path: "/admin/theaters", body: { name: "西幽剧场", default_weekly_template: { monday: ["early"] } } });
expect(requests).toContainEqual({ path: "/admin/roles", body: { name: "长离", group_name: "女位" } });
```

The fetch stub must return created objects for POST and accumulated arrays for later GET requests.

- [ ] **Step 2: Run the settings test and verify RED**

Run: `cd frontend && npm run test -- --run tests/admin-workflows.test.tsx`

Expected: inputs and save buttons are missing.

- [ ] **Step 3: Implement inline settings forms**

In `SettingsPage.tsx`, add controlled `theaterName`, `weeklyTemplate`, `roleName`, `groupName`, and `error` state. Render seven weekday rows with early/late checkboxes and these accessible labels:

```tsx
<input aria-label="剧场名称" value={theaterName} onChange={(event) => setTheaterName(event.target.value)} />
<label><input type="checkbox" checked={weeklyTemplate.monday?.includes("early") ?? false} onChange={() => toggleSlot("monday", "early")} />周一早场</label>
<button type="submit">保存剧场</button>
<input aria-label="角色名称" value={roleName} onChange={(event) => setRoleName(event.target.value)} />
<input aria-label="角色分组" value={groupName} onChange={(event) => setGroupName(event.target.value)} />
<button type="submit">保存角色</button>
{error && <p role="alert">{error}</p>}
```

`saveTheater` calls `createTheater`, clears the name, then refreshes theaters. `saveRole` calls `createRole`, clears both inputs, then refreshes roles. Both catch `Error` and set its message.

- [ ] **Step 4: Run settings tests and build**

Run: `cd frontend && npm run test -- --run tests/admin-workflows.test.tsx && npm run build`

Expected: tests and build pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/SettingsPage.tsx frontend/tests/admin-workflows.test.tsx
git commit -m "feat: add theater and role entry forms"
```

---

### Task 4: Actor Entry, Editing, and Capabilities UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/admin/ActorsPage.tsx`
- Modify: `frontend/tests/admin-workflows.test.tsx`

**Interfaces:**
- Produces `apiClient.updateActor(token, actorId, payload) -> Promise<Actor>`.
- Produces `apiClient.replaceActorCapabilities(token, actorId, roleIds) -> Promise<Actor>`.

- [ ] **Step 1: Add failing actor mutation tests**

Add a test whose fetch stub returns one role and supports actor POST/PATCH/PUT. The test opens 演员管理, fills `演员姓名`, selects `演员评级`, fills `最大连场`, submits `保存演员`, then edits the returned actor row, checks `长离`, and clicks `保存演员设置`. Assert:

```ts
expect(requests).toContainEqual({ method: "POST", path: "/admin/actors" });
expect(requests).toContainEqual({ method: "PATCH", path: "/admin/actors/1" });
expect(requests).toContainEqual({ method: "PUT", path: "/admin/actors/1/capabilities", body: { role_ids: [1] } });
```

- [ ] **Step 2: Run the actor test and verify RED**

Run: `cd frontend && npm run test -- --run tests/admin-workflows.test.tsx`

Expected: actor form fields and working save controls are missing.

- [ ] **Step 3: Add typed client methods and error details**

Add a public `put` helper and methods to `ApiClient`:

```ts
async updateActor(token: string, actorId: number, payload: Omit<Actor, "id" | "display_name" | "role_ids">): Promise<Actor> {
  return this.request(`/admin/actors/${actorId}`, token, "PATCH", payload);
}

async replaceActorCapabilities(token: string, actorId: number, roleIds: number[]): Promise<Actor> {
  return this.request(`/admin/actors/${actorId}/capabilities`, token, "PUT", { role_ids: roleIds });
}
```

Refactor `get` and `post` through `request<T>`. When a response is not OK, parse JSON and throw `new Error(body.detail ?? "请求失败")`.

- [ ] **Step 4: Implement actor forms**

Load roles alongside actors. Add an inline create form with defaults `rating_level: "normal"`, `max_consecutive_performances: 3`, null cap, and null notes. Render each actor as an `ActorEditor` component with controlled rating, consecutive limit, cap, notes, and role IDs. Its save action must sequentially call `updateActor` and `replaceActorCapabilities`, then invoke a parent refresh. Render errors with `role="alert"`.

- [ ] **Step 5: Run actor tests and build**

Run: `cd frontend && npm run test -- --run tests/admin-workflows.test.tsx && npm run build`

Expected: tests and build pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/admin/ActorsPage.tsx frontend/tests/admin-workflows.test.tsx
git commit -m "feat: add actor administration forms"
```

---

### Task 5: Monthly Plan Generation UI

**Files:**
- Modify: `frontend/src/pages/admin/MonthlyPlanPage.tsx`
- Modify: `frontend/tests/admin-workflows.test.tsx`

**Interfaces:**
- Consumes `generateMonthlyPlan(token, { theater_id, year, month, closed_dates })`.
- Produces selectable theater/year/month, closed-date input, generation action, and visible errors.

- [ ] **Step 1: Replace the read-only monthly test with a failing generation test**

The test stub returns a theater, an empty performance GET, and a generated performance for POST. Open 月度计划, select 西幽剧场, set year `2027`, month `7`, fill `闭店日期` with `2027-07-02, 2027-07-09`, click `生成月度计划`, then assert the POST body and rendered `2027-07-01 early`.

```ts
expect(generateBody).toEqual({ theater_id: 1, year: 2027, month: 7, closed_dates: ["2027-07-02", "2027-07-09"] });
```

- [ ] **Step 2: Run the monthly test and verify RED**

Run: `cd frontend && npm run test -- --run tests/admin-workflows.test.tsx`

Expected: the date controls and generation button are missing.

- [ ] **Step 3: Implement monthly controls and error handling**

Replace fixed year/month state with controlled values. Render:

```tsx
<select aria-label="选择剧场" value={theaterId} onChange={(event) => setTheaterId(Number(event.target.value))}>...</select>
<input aria-label="年份" type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} />
<input aria-label="月份" type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} />
<textarea aria-label="闭店日期" value={closedDates} onChange={(event) => setClosedDates(event.target.value)} />
<button type="button" onClick={generate}>生成月度计划</button>
{error && <p role="alert">{error}</p>}
```

Parse dates with `closedDates.split(/[\n,]/).map(value => value.trim()).filter(Boolean)`. `generate` requires a selected theater, calls the client, and replaces `performances` with the response.

- [ ] **Step 4: Run all frontend checks**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: all frontend tests pass and production build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/MonthlyPlanPage.tsx frontend/tests/admin-workflows.test.tsx
git commit -m "feat: add monthly plan generation controls"
```

---

### Task 6: Final Verification and Acceptance Audit

**Files:**
- Modify if required by evidence: `docs/superpowers/acceptance-checklist.md`

- [ ] **Step 1: Run backend verification**

Run:

```bash
backend/.venv/bin/ruff check backend
cd backend && pytest -q
```

Expected: Ruff succeeds and all backend tests pass.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cd frontend && npm run test -- --run && npm run build
```

Expected: all frontend tests pass and Vite build succeeds.

- [ ] **Step 3: Audit acceptance claims against tests**

Keep the six `Admin Foundation Added` items checked only when the new mutation and safety tests pass. Do not mark any item in `Remaining V1 Work` complete. If wording changed, update `docs/superpowers/acceptance-checklist.md` to match observed capability.

- [ ] **Step 4: Verify repository hygiene**

Run:

```bash
git diff --check
git ls-files | rg '(__pycache__|\.pyc$|frontend/dist|egg-info|node_modules|backend/\.venv)'
git status --short
```

Expected: no whitespace errors, no generated files listed, and no unintended changes.

- [ ] **Step 5: Commit documentation changes if any**

```bash
git add docs/superpowers/acceptance-checklist.md
git commit -m "docs: verify admin foundation acceptance"
```

Skip this commit only if the checklist needs no changes.

---

## Self-Review

- Spec coverage: template validation and atomic capabilities are Task 1; regeneration safety is Task 2; theater/role entry is Task 3; actor creation/editing/capabilities is Task 4; selectable monthly generation is Task 5; verification and acceptance accuracy are Task 6.
- Scope: no deletes, generic CRUD framework, dialogs, wizard, weekly scheduling editor, publish, or export work is included.
- Type consistency: actor update and capability method payloads match the existing backend schemas; monthly-plan payload uses `theater_id`, numeric `year`/`month`, and string `closed_dates` converted by FastAPI to dates.
- No placeholders or deferred implementation steps remain.
