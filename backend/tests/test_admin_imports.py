from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    ImportDraftItem,
    Performance,
    PersistentImportDraft,
    Role,
    Theater,
    WeeklyBatch,
    Wish,
)
from app.models.enums import (
    BatchStatus,
    ImportDraftStatus,
    DraftItemKind,
    DraftValidationStatus,
    DesignationType,
)
from app.schemas.admin_imports import DraftItemCreate, DraftItemUpdate
from app.services.admin_imports import (
    DraftItemConflict,
    confirm_draft_item,
    create_manual_item,
    get_batch_scheduling_inputs,
    get_or_create_weekly_batch,
    parse_import_draft,
    update_draft_item,
)
from app.services.auth import create_access_token


def test_weekly_batch_and_import_draft_relationships(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    db_session.add(batch)
    db_session.flush()

    draft = PersistentImportDraft(weekly_batch_id=batch.id, raw_text="测试文本")
    db_session.add(draft)
    db_session.flush()

    item = ImportDraftItem(
        import_draft_id=draft.id, item_kind=DraftItemKind.UNRESOLVED, raw_line="浩泽 想要 演 长离"
    )
    db_session.add(item)
    db_session.commit()

    db_session.refresh(batch)
    db_session.refresh(draft)
    db_session.refresh(item)

    assert batch.status == BatchStatus.DRAFT
    assert draft.status == ImportDraftStatus.DRAFT
    assert item.validation_status == DraftValidationStatus.INVALID
    assert item.import_draft.id == draft.id
    assert draft.weekly_batch.id == batch.id


def test_duplicate_weekly_batches_raise_integrity_error(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch1 = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    batch2 = WeeklyBatch(theater_id=theater.id, week_start=date(2026, 6, 1))
    db_session.add(batch1)
    db_session.add(batch2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_get_or_create_weekly_batch_validation_and_idempotency(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    # Non-Monday date should raise ValueError
    with pytest.raises(ValueError, match="week_start_must_be_monday"):
        get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 2))  # Tuesday

    # Creation
    batch1 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    db_session.commit()

    # Repeated query/creation returns existing
    batch2 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    assert batch1.id == batch2.id


def test_parse_import_draft_persists_items(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    db_session.commit()

    text = """
#指定信息⬇️
【虔诚许愿】-小展/长离-Jennifer 山风昭昭可以原地转十个圈
热力榜三-文轩/轩辕重光（四月热力榜-兹）
未知行：什么都没有匹配
"""
    draft = parse_import_draft(db_session, batch.id, text)
    db_session.commit()
    db_session.expire_all()

    # Verify persistent draft and its items
    refreshed_draft = db_session.get(PersistentImportDraft, draft.id)
    assert refreshed_draft is not None
    assert len(refreshed_draft.items) == 3

    # Check kind
    kinds = [item.item_kind for item in refreshed_draft.items]
    assert DraftItemKind.WISH in kinds
    assert DraftItemKind.DESIGNATION in kinds
    assert DraftItemKind.UNRESOLVED in kinds


def test_item_validation_and_corrections(db_session):
    # Setup theater, batch, actor, role, capability
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))

    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()

    # Cap not added yet.
    draft = parse_import_draft(
        db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry 想要长离"
    )
    db_session.commit()

    item = draft.items[0]
    # Should be invalid because of missing capability
    assert item.validation_status == DraftValidationStatus.INVALID
    assert item.failure_reason == "actor_role_capability_missing"

    # Fix capability
    cap = ActorRoleCapability(actor_id=actor.id, role_id=role.id)
    db_session.add(cap)
    db_session.commit()

    # Update item to trigger re-validation
    update_payload = DraftItemUpdate(
        item_kind=item.item_kind,
        designation_type=item.designation_type,
        player_name=item.player_name,
        actor_name_raw=item.actor_name_raw,
        role_name_raw=item.role_name_raw,
        actor_id=actor.id,
        role_id=role.id,
        note=item.note,
    )
    updated_item = update_draft_item(db_session, item.id, update_payload)
    db_session.commit()

    assert updated_item.validation_status == DraftValidationStatus.VALID
    assert updated_item.failure_reason is None


def test_performance_outside_batch_validation(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    other_theater = Theater(name="另一个剧场", default_weekly_template={})
    db_session.add_all([theater, other_theater])
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))

    # Performance belonging to another theater
    perf_other = Performance(
        theater_id=other_theater.id, performance_date=date(2026, 6, 1), slot="early"
    )
    # Performance outside Monday to Sunday week range
    perf_outside = Performance(
        theater_id=theater.id, performance_date=date(2026, 6, 8), slot="early"
    )

    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([perf_other, perf_outside, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    draft = parse_import_draft(db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry")
    item = draft.items[0]

    # Convert to designation, and target invalid performance (wrong theater)
    payload = DraftItemUpdate(
        item_kind=DraftItemKind.DESIGNATION,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jerry",
        actor_name_raw="浩泽",
        role_name_raw="长离",
        actor_id=actor.id,
        role_id=role.id,
        target_performance_id=perf_other.id,
    )
    updated = update_draft_item(db_session, item.id, payload)
    assert updated.validation_status == DraftValidationStatus.INVALID
    assert updated.failure_reason == "performance_outside_batch"

    # Target outside date range performance
    payload.target_performance_id = perf_outside.id
    updated = update_draft_item(db_session, item.id, payload)
    assert updated.validation_status == DraftValidationStatus.INVALID
    assert updated.failure_reason == "performance_outside_batch"


def test_partial_confirmation_and_idempotency(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    # Draft with one valid wish and one unresolved (invalid) designation
    draft = parse_import_draft(
        db_session, batch.id, "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry\n未知行：无效数据"
    )
    item_wish = next(i for i in draft.items if i.item_kind == DraftItemKind.WISH)
    item_unresolved = next(i for i in draft.items if i.item_kind == DraftItemKind.UNRESOLVED)

    assert item_wish.validation_status == DraftValidationStatus.VALID
    assert item_unresolved.validation_status == DraftValidationStatus.INVALID

    # Confirm the valid wish
    confirmed = confirm_draft_item(db_session, item_wish.id)
    db_session.commit()

    db_session.refresh(draft)
    assert draft.status == ImportDraftStatus.PARTIALLY_CONFIRMED
    assert db_session.query(Wish).count() == 1

    # Idempotent confirmation returns existing
    confirmed_again = confirm_draft_item(db_session, item_wish.id)
    assert confirmed.wish_id == confirmed_again.wish_id
    assert db_session.query(Wish).count() == 1

    # Confirming invalid item fails
    with pytest.raises(DraftItemConflict, match="draft_item_invalid"):
        confirm_draft_item(db_session, item_unresolved.id)

    # Correct invalid item to designation
    update_payload = DraftItemUpdate(
        item_kind=DraftItemKind.DESIGNATION,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jerry",
        actor_name_raw="浩泽",
        role_name_raw="长离",
        actor_id=actor.id,
        role_id=role.id,
    )
    corrected_item = update_draft_item(db_session, item_unresolved.id, update_payload)
    db_session.commit()

    assert corrected_item.validation_status == DraftValidationStatus.VALID

    # Confirm the corrected designation
    confirm_draft_item(db_session, corrected_item.id)
    db_session.commit()

    db_session.refresh(draft)
    assert draft.status == ImportDraftStatus.CONFIRMED
    assert db_session.query(Designation).count() == 1


def test_batch_scheduling_inputs(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()

    batch1 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    batch2 = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 8))

    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    # Confirmed records on batch1
    d1 = Designation(
        weekly_batch_id=batch1.id,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Jerry",
        actor_id=actor.id,
        role_id=role.id,
        submitted_at=datetime.utcnow(),
        included_in_batch=True,
        status="confirmed",
    )
    w1 = Wish(
        weekly_batch_id=batch1.id,
        player_name="Jerry",
        actor_id=actor.id,
        role_id=role.id,
        note="备注1",
    )

    # Confirmed records on batch2 (should be excluded from batch1)
    d2 = Designation(
        weekly_batch_id=batch2.id,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Tom",
        actor_id=actor.id,
        role_id=role.id,
        submitted_at=datetime.utcnow(),
        included_in_batch=True,
        status="confirmed",
    )

    # Unconfirmed/not-included designations on batch1 (should be excluded)
    d1_unconfirmed = Designation(
        weekly_batch_id=batch1.id,
        designation_type=DesignationType.UNIVERSAL,
        player_name="Spike",
        actor_id=actor.id,
        role_id=role.id,
        submitted_at=datetime.utcnow(),
        included_in_batch=False,
        status="pending",
    )

    db_session.add_all([d1, w1, d2, d1_unconfirmed])
    db_session.commit()

    inputs = get_batch_scheduling_inputs(db_session, batch1.id)
    assert len(inputs["designations"]) == 1
    assert inputs["designations"][0]["player_name"] == "Jerry"
    assert len(inputs["wishes"]) == 1
    assert inputs["wishes"][0]["player_name"] == "Jerry"
    assert w1.note == "备注1"


def test_admin_imports_api_workflow(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    actor = Actor(display_name="浩泽")
    role = Role(name="长离")
    db_session.add_all([theater, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        token = create_access_token("admin@example.com", "admin")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. POST /admin/weekly-batches (create batch)
        res_batch = client.post(
            "/admin/weekly-batches",
            headers=headers,
            json={"theater_id": theater.id, "week_start": "2026-06-01"},
        )
        assert res_batch.status_code == 200
        batch_id = res_batch.json()["id"]

        # 2. GET /admin/weekly-batches (list batches)
        res_list = client.get("/admin/weekly-batches", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1

        # 3. GET /admin/weekly-batches/{batch_id}
        res_get_batch = client.get(f"/admin/weekly-batches/{batch_id}", headers=headers)
        assert res_get_batch.status_code == 200

        res_ready = client.patch(
            f"/admin/weekly-batches/{batch_id}/status",
            headers=headers,
            json={"status": "ready"},
        )
        assert res_ready.status_code == 200
        assert res_ready.json()["status"] == "ready"

        res_reopen = client.patch(
            f"/admin/weekly-batches/{batch_id}/status",
            headers=headers,
            json={"status": "draft"},
        )
        assert res_reopen.status_code == 409

        # 4. POST /admin/import-drafts/parse
        res_parse = client.post(
            f"/admin/import-drafts/parse?batch_id={batch_id}",
            headers=headers,
            json={"raw_text": "#指定信息\n【虔诚许愿】-浩泽/长离-Jerry\n未知行：不合规"},
        )
        assert res_parse.status_code == 200
        draft_id = res_parse.json()["id"]
        assert len(res_parse.json()["items"]) == 2

        # Find items
        item_wish = next(i for i in res_parse.json()["items"] if i["item_kind"] == "wish")
        item_unresolved = next(
            i for i in res_parse.json()["items"] if i["item_kind"] == "unresolved"
        )

        # 5. GET /admin/import-drafts/{draft_id}
        res_draft = client.get(f"/admin/import-drafts/{draft_id}", headers=headers)
        assert res_draft.status_code == 200

        # 6. POST /admin/import-drafts/{draft_id}/items (manual item creation)
        res_manual = client.post(
            f"/admin/import-drafts/{draft_id}/items",
            headers=headers,
            json={
                "item_kind": "wish",
                "player_name": "Tom",
                "actor_name_raw": "浩泽",
                "role_name_raw": "长离",
            },
        )
        assert res_manual.status_code == 200

        # 7. PATCH /admin/import-draft-items/{item_id} (correct unresolved to valid designation)
        res_patch = client.patch(
            f"/admin/import-draft-items/{item_unresolved['id']}",
            headers=headers,
            json={
                "item_kind": "designation",
                "designation_type": "universal",
                "player_name": "Jerry",
                "actor_name_raw": "浩泽",
                "role_name_raw": "长离",
            },
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["validation_status"] == "valid"

        # 8. POST /admin/import-draft-items/{item_id}/confirm
        res_confirm = client.post(
            f"/admin/import-draft-items/{item_wish['id']}/confirm",
            headers=headers,
        )
        assert res_confirm.status_code == 200

        # 9. POST /admin/import-drafts/{draft_id}/confirm-valid
        res_confirm_all = client.post(
            f"/admin/import-drafts/{draft_id}/confirm-valid",
            headers=headers,
        )
        assert res_confirm_all.status_code == 200

        # 10. GET /admin/weekly-batches/{batch_id}/scheduling-inputs
        res_inputs = client.get(
            f"/admin/weekly-batches/{batch_id}/scheduling-inputs", headers=headers
        )
        assert res_inputs.status_code == 200
        assert len(res_inputs.json()["designations"]) == 1
        assert len(res_inputs.json()["wishes"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_selected_actor_and_role_ids_override_unmatched_raw_names(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    actor = Actor(display_name="正确演员")
    role = Role(name="正确角色")
    db_session.add_all([theater, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    draft = PersistentImportDraft(weekly_batch_id=batch.id, raw_text="")
    db_session.add(draft)
    db_session.flush()
    item = create_manual_item(
        db_session,
        draft.id,
        DraftItemCreate(
            item_kind=DraftItemKind.WISH,
            player_name="玩家甲",
            actor_name_raw="错误演员",
            role_name_raw="错误角色",
            actor_id=actor.id,
            role_id=role.id,
        ),
    )
    assert item.validation_status == DraftValidationStatus.VALID
    assert item.actor_id == actor.id
    assert item.role_id == role.id


@pytest.mark.parametrize(
    "payload",
    [
        DraftItemCreate(item_kind=DraftItemKind.WISH, player_name=None),
        DraftItemCreate(item_kind=DraftItemKind.DESIGNATION, player_name="玩家甲"),
    ],
)
def test_missing_required_fields_remain_invalid(db_session, payload):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()
    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    draft = PersistentImportDraft(weekly_batch_id=batch.id, raw_text="")
    db_session.add(draft)
    db_session.flush()
    item = create_manual_item(db_session, draft.id, payload)
    assert item.validation_status == DraftValidationStatus.INVALID
    assert item.failure_reason in {"player_name_required", "designation_type_required"}


def test_adding_item_reopens_confirmed_draft(db_session):
    theater = Theater(name="测试剧场", default_weekly_template={})
    db_session.add(theater)
    db_session.flush()
    batch = get_or_create_weekly_batch(db_session, theater.id, date(2026, 6, 1))
    draft = PersistentImportDraft(
        weekly_batch_id=batch.id,
        raw_text="",
        status=ImportDraftStatus.CONFIRMED,
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(
        ImportDraftItem(
            import_draft_id=draft.id,
            item_kind=DraftItemKind.WISH,
            player_name="已确认玩家",
            confirmed_at=datetime(2026, 6, 1, 12, 0),
        )
    )
    db_session.commit()
    create_manual_item(
        db_session,
        draft.id,
        DraftItemCreate(item_kind=DraftItemKind.WISH, player_name="玩家甲"),
    )
    db_session.refresh(draft)
    assert draft.status == ImportDraftStatus.PARTIALLY_CONFIRMED
