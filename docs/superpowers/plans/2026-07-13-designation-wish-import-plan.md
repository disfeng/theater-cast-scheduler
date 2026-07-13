# Designation and Wish Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build persistent weekly batches and import drafts so administrators can parse, correct, partially confirm, and schedule confirmed designations and wishes.

**Architecture:** Add normalized SQLAlchemy records for weekly batches, import drafts, and draft items, then keep parsing/matching/confirmation in a focused service with transaction boundaries. Expose admin-only HTTP adapters and a React page whose state is always recoverable from the API.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, MySQL 8.0, pytest, TypeScript, React, Vitest, Testing Library, Vite.

## Global Constraints

- Work directly on `main`, as explicitly requested for V1.
- Use TDD for every behavior change and commit each independently testable task.
- A weekly batch is unique by theater and Monday `week_start`.
- Valid draft items may be confirmed while invalid items remain unresolved.
- Confirmation is idempotent per draft item.
- Unresolved or invalid records never enter formal designation or wish tables.
- Wishes are weekly; only designations may target a specific performance.
- Keep generated files out of Git.

---

## File Structure

```text
backend/app/models/entities.py                         batch and persistent draft models
backend/app/models/enums.py                            batch/draft/item statuses
backend/app/schemas/admin_imports.py                    request and response contracts
backend/app/services/admin_imports.py                   batch, parse, match, edit, confirm
backend/app/api/routes/admin_imports.py                 admin-only HTTP adapters
backend/app/main.py                                     router registration
backend/migrations/versions/0003_add_import_drafts.py   MySQL-compatible schema migration
backend/tests/test_admin_imports.py                     service and API behavior
backend/tests/test_migration_files.py                   migration smoke assertions
frontend/src/api/client.ts                              typed import APIs
frontend/src/components/AppShell.tsx                    navigation entry
frontend/src/pages/admin/DesignationWishPage.tsx        persistent draft UI
frontend/tests/import-workflows.test.tsx                admin workflow coverage
docs/superpowers/acceptance-checklist.md                verified acceptance update
```

---

### Task 1: Weekly Batch and Import Draft Persistence

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/entities.py`
- Create: `backend/migrations/versions/0003_add_import_drafts.py`
- Create: `backend/tests/test_admin_imports.py`
- Modify: `backend/tests/test_migration_files.py`

**Interfaces:**
- Produces `WeeklyBatch`, `PersistentImportDraft`, and `ImportDraftItem` ORM models.
- Produces `BatchStatus`, `ImportDraftStatus`, `DraftItemKind`, and `DraftValidationStatus` enums.

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/test_admin_imports.py` with a test that inserts one theater, a `WeeklyBatch(theater_id=..., week_start=date(2026, 6, 1))`, a draft, and one unresolved item, then asserts relationships and default statuses. Add a second test that inserting two batches with the same theater/week raises `IntegrityError`.

- [ ] **Step 2: Run the model tests and verify RED**

Run: `cd backend && pytest tests/test_admin_imports.py -q`

Expected: import failure because the models do not exist.

- [ ] **Step 3: Add enums and ORM models**

Add string enums with values from the approved spec. Implement:

```python
class WeeklyBatch(Base):
    __tablename__ = "weekly_batches"
    __table_args__ = (UniqueConstraint("theater_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus), default=BatchStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Create `PersistentImportDraft` and `ImportDraftItem` with every field and relationship specified in the design. Add nullable `weekly_batch_id` foreign keys to `Designation` and `Wish`.

- [ ] **Step 4: Add migration and smoke assertions**

Create revision `0003_add_import_drafts`, revising `0002_add_monthly_plan_support`. Create the three tables, indexes, unique batch constraint, and both formal-record foreign keys; downgrade reverses them in dependency order. Extend the migration smoke test to assert the revision, table names, `weekly_batch_id`, and unique batch constraint.

- [ ] **Step 5: Run Task 1 tests and backend models regression**

Run: `cd backend && pytest tests/test_admin_imports.py tests/test_migration_files.py tests/test_models.py -q`

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/entities.py backend/migrations/versions/0003_add_import_drafts.py backend/tests/test_admin_imports.py backend/tests/test_migration_files.py
git commit -m "feat: add weekly batch import persistence"
```

---

### Task 2: Batch Creation and Persistent Parsing

**Files:**
- Create: `backend/app/schemas/admin_imports.py`
- Create: `backend/app/services/admin_imports.py`
- Modify: `backend/tests/test_admin_imports.py`

**Interfaces:**
- Produces `get_or_create_weekly_batch(db, theater_id, week_start) -> WeeklyBatch`.
- Produces `parse_import_draft(db, batch_id, raw_text) -> PersistentImportDraft`.
- Produces Pydantic contracts `WeeklyBatchCreate`, `WeeklyBatchRead`, `ImportParseRequest`, `ImportDraftRead`, and `DraftItemRead`.

- [ ] **Step 1: Add failing batch and parse tests**

Test that a non-Monday date raises `ValueError("week_start_must_be_monday")`, repeated creation returns the existing batch, and parsing the existing group-board fixture persists a wish, a top-three designation suggestion, and unresolved lines after `expire_all()`.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `cd backend && pytest tests/test_admin_imports.py -q`

Expected: service module or functions are missing.

- [ ] **Step 3: Implement batch creation**

Validate `week_start.weekday() == 0`, validate the theater exists, select by theater/week, and return the existing record or insert a new draft batch.

- [ ] **Step 4: Implement parsing and initial matching**

Call `parse_group_board(raw_text)`. Convert wishes, designation suggestions, and unresolved lines into `ImportDraftItem` rows. Match actor and role by exact trimmed names. Set `failure_reason` in this order: `actor_not_found`, `role_not_found`, `actor_role_capability_missing`; otherwise mark `valid`. Keep unresolved items invalid with raw lines intact.

- [ ] **Step 5: Run parse tests and verify GREEN**

Run: `cd backend && pytest tests/test_admin_imports.py -q`

Expected: all Task 1–2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/admin_imports.py backend/app/services/admin_imports.py backend/tests/test_admin_imports.py
git commit -m "feat: persist weekly import drafts"
```

---

### Task 3: Draft Editing, Partial Confirmation, and Scheduling Inputs

**Files:**
- Modify: `backend/app/schemas/admin_imports.py`
- Modify: `backend/app/services/admin_imports.py`
- Modify: `backend/tests/test_admin_imports.py`

**Interfaces:**
- Produces `create_manual_item(db, draft_id, payload) -> ImportDraftItem`.
- Produces `update_draft_item(db, item_id, payload) -> ImportDraftItem`.
- Produces `confirm_draft_item(db, item_id) -> ImportDraftItem`.
- Produces `confirm_valid_items(db, draft_id) -> list[ConfirmationResult]`.
- Produces `get_batch_scheduling_inputs(db, batch_id) -> BatchSchedulingInputs`.

- [ ] **Step 1: Add failing validation and edit tests**

Cover actor/role correction, capability validation, and rejecting a target performance belonging to another theater or outside `week_start..week_start+6` with `performance_outside_batch`. Cover converting an unresolved item to a designation or wish.

- [ ] **Step 2: Run edit tests and verify RED**

Run the named tests in `backend/tests/test_admin_imports.py`; expect missing methods.

- [ ] **Step 3: Implement shared item validation**

Write one `_validate_item(db, item)` function used after parse, manual creation, update, and immediately before confirmation. Wishes must clear `target_performance_id`; designations may leave it null. Persist `validation_status` and stable `failure_reason`.

- [ ] **Step 4: Add failing partial-confirmation and idempotency tests**

Create a draft containing one valid wish and one invalid designation. Confirm the valid item and assert the invalid item remains, draft status becomes `partially_confirmed`, and only one formal record exists. Confirm the same item again and assert the same formal ID and row count. After correcting the invalid item, confirm it and assert draft status becomes `confirmed`.

- [ ] **Step 5: Implement transactional confirmation**

Reload and validate the item. If `designation_id` or `wish_id` is already set, return it unchanged. If invalid, raise `DraftItemConflict("draft_item_invalid")`. Create the proper formal entity with `weekly_batch_id`, set `included_in_batch=True` for designations, set `confirmed_at`, update aggregate draft status, and commit once. Roll back on all exceptions.

- [ ] **Step 6: Add and implement scheduling-input tests**

Assert only confirmed formal records for the requested batch are returned and values equal `DesignationInput` and `WishInput` field shapes. Records from another batch and unconfirmed items must be excluded.

- [ ] **Step 7: Run service tests and commit**

Run: `cd backend && pytest tests/test_admin_imports.py -q`

```bash
git add backend/app/schemas/admin_imports.py backend/app/services/admin_imports.py backend/tests/test_admin_imports.py
git commit -m "feat: confirm import drafts into scheduling inputs"
```

---

### Task 4: Admin Import APIs

**Files:**
- Create: `backend/app/api/routes/admin_imports.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_admin_imports.py`

**Interfaces:**
- Produces every admin route listed in the approved design.
- Maps missing records to 404, invalid input to 422, and draft business conflicts to 409.

- [ ] **Step 1: Add failing API workflow tests**

Using `TestClient` and an admin token, create/open a batch, parse text, fetch the persisted draft, patch an item, confirm one item, confirm all valid items, and fetch scheduling inputs. Add authentication and 409 conflict assertions.

- [ ] **Step 2: Run API tests and verify RED**

Run: `cd backend && pytest tests/test_admin_imports.py -q`

Expected: new routes return 404.

- [ ] **Step 3: Implement router adapters**

Create an `/admin` router with the exact route paths from the spec. Keep conversions in `_batch_read`, `_draft_read`, and `_item_read` helpers. Route handlers call services only and translate `LookupError`, `ValueError`, and `DraftItemConflict` consistently.

- [ ] **Step 4: Register router and run backend regression**

Include `admin_imports.router` in `app/main.py`. Run:

```bash
cd backend && pytest tests/test_admin_imports.py -q
cd .. && backend/.venv/bin/ruff check backend
```

Expected: API tests and Ruff pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/admin_imports.py backend/app/main.py backend/tests/test_admin_imports.py
git commit -m "feat: expose designation and wish import APIs"
```

---

### Task 5: Persistent Import Administration UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/pages/admin/DesignationWishPage.tsx`
- Create: `frontend/tests/import-workflows.test.tsx`

**Interfaces:**
- Produces typed client methods for batches, parse, draft fetch, manual item creation, item patch, item confirmation, and confirm-valid.
- Produces admin navigation item `指定与许愿`.

- [ ] **Step 1: Add a failing parse-and-resume UI test**

Stub the APIs, log in, navigate to 指定与许愿, select theater, enter a Monday, click 创建/打开批次, paste group-board text, and click 解析。Assert the draft rows and failure reasons render. Unmount and render again with the server returning the existing draft; assert it is restored.

- [ ] **Step 2: Run the UI test and verify RED**

Run: `cd frontend && npm run test -- --run tests/import-workflows.test.tsx`

Expected: navigation and page are missing.

- [ ] **Step 3: Extend the typed API client**

Define `WeeklyBatch`, `ImportDraft`, `ImportDraftItem`, and payload types. Add methods matching all new routes. Reuse the existing structured-error formatter.

- [ ] **Step 4: Build batch and parse controls**

The page loads theaters, accepts a Monday date, creates/opens a batch, accepts raw text, parses it, and renders the server-returned draft. Store only selected IDs in component state; always refresh the full draft from the server after mutations.

- [ ] **Step 5: Add failing correction, manual-entry, and confirmation tests**

Cover changing kind/type/actor/role/performance, row-level confirm, confirm-all-valid, unresolved-to-record conversion, manual designation, manual wish, and row/page error display.

- [ ] **Step 6: Implement draft table and manual entry**

Use inline selects sourced from theaters, actors, roles, and batch performances. Disable controls for confirmed rows. Render stable error codes as readable Chinese labels while retaining the code for diagnostics.

- [ ] **Step 7: Run frontend tests and build**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: all tests pass and production build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/AppShell.tsx frontend/src/pages/admin/DesignationWishPage.tsx frontend/tests/import-workflows.test.tsx
git commit -m "feat: add persistent designation and wish import UI"
```

---

### Task 6: Final Verification and Acceptance

**Files:**
- Modify: `docs/superpowers/acceptance-checklist.md`

- [ ] **Step 1: Run the complete backend quality gate**

```bash
backend/.venv/bin/ruff check backend
cd backend && pytest -q
```

- [ ] **Step 2: Run the complete frontend quality gate**

```bash
cd frontend && npm run test -- --run && npm run build
```

- [ ] **Step 3: Update acceptance evidence**

Mark “指定/许愿正式录入、导入确认和周批次纳入” complete only when persistence, partial confirmation, idempotency, scheduling-input, and UI tests all pass. Keep weekly scheduling, publish/export, and MySQL instance verification unchecked.

- [ ] **Step 4: Verify repository hygiene**

```bash
git diff --check
git ls-files | rg '(__pycache__|\.pyc$|frontend/dist|egg-info|node_modules|backend/\.venv)'
git status --short
```

Expected: no whitespace errors, no generated files tracked, and only intended changes.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/acceptance-checklist.md
git commit -m "docs: record import workflow acceptance"
```

---

## Self-Review

- Data persistence and migration are Task 1.
- Batch identity and persistent parsing are Task 2.
- Matching, correction, partial confirmation, idempotency, and scheduling inputs are Task 3.
- All approved admin API paths and error mappings are Task 4.
- Persistent UI, manual entry, correction, confirmation, recovery, and errors are Task 5.
- Quality gates and accurate acceptance status are Task 6.
- Weekly scheduling UI, publishing, export, players, and fuzzy matching remain explicitly out of scope.
