from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now

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
    DesignationType,
    DraftItemKind,
    DraftValidationStatus,
    ImportDraftStatus,
)
from app.schemas.admin_imports import DraftItemCreate, DraftItemUpdate
from app.services.import_parser import parse_group_board


class DraftItemConflict(Exception):
    pass


def _get_editable_batch(db: Session, batch_id: int) -> WeeklyBatch:
    batch = db.scalar(
        select(WeeklyBatch)
        .where(WeeklyBatch.id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise LookupError("batch_not_found")
    if batch.status != BatchStatus.DRAFT:
        raise DraftItemConflict("batch_not_editable")
    return batch


def _require_editable_batch(db: Session, draft: PersistentImportDraft) -> WeeklyBatch:
    return _get_editable_batch(db, draft.weekly_batch_id)


def get_or_create_weekly_batch(db: Session, theater_id: int, week_start: date) -> WeeklyBatch:
    if week_start.weekday() != 0:
        raise ValueError("week_start_must_be_monday")

    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")

    batch = db.scalar(
        select(WeeklyBatch).where(
            WeeklyBatch.theater_id == theater_id,
            WeeklyBatch.week_start == week_start,
        )
    )
    if batch is not None:
        return batch

    batch = WeeklyBatch(theater_id=theater_id, week_start=week_start, status=BatchStatus.DRAFT)
    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        batch = db.scalar(
            select(WeeklyBatch).where(
                WeeklyBatch.theater_id == theater_id,
                WeeklyBatch.week_start == week_start,
            )
        )
        if batch is None:
            raise
    db.refresh(batch)
    return batch


def parse_import_draft(db: Session, batch_id: int, raw_text: str) -> PersistentImportDraft:
    batch = _get_editable_batch(db, batch_id)

    draft = PersistentImportDraft(
        weekly_batch_id=batch_id,
        raw_text=raw_text,
        status=ImportDraftStatus.DRAFT,
    )
    db.add(draft)
    db.flush()

    parsed = parse_group_board(raw_text)

    # 1. Wishes
    for wish in parsed.wishes:
        item = ImportDraftItem(
            import_draft_id=draft.id,
            item_kind=DraftItemKind.WISH,
            raw_line=f"【虔诚许愿】-{wish.actor_name}/{wish.role_name}-{wish.player_name} {wish.raw_note}",
            player_name=wish.player_name,
            actor_name_raw=wish.actor_name,
            role_name_raw=wish.role_name,
            note=wish.raw_note,
        )
        db.add(item)
        db.flush()
        _validate_item(db, item, batch)

    # 2. Designation suggestions
    for sug in parsed.designation_suggestions:
        item = ImportDraftItem(
            import_draft_id=draft.id,
            item_kind=DraftItemKind.DESIGNATION,
            raw_line=sug.raw_line,
            designation_type=DesignationType.TOP_THREE
            if sug.suggested_type == "top_three"
            else DesignationType.PAIRED,
            player_name=sug.player_name,
            actor_name_raw=sug.actor_name,
            role_name_raw=sug.role_name,
        )
        db.add(item)
        db.flush()
        _validate_item(db, item, batch)

    # 3. Unresolved lines
    for line in parsed.unresolved_lines:
        item = ImportDraftItem(
            import_draft_id=draft.id,
            item_kind=DraftItemKind.UNRESOLVED,
            raw_line=line,
            validation_status=DraftValidationStatus.INVALID,
        )
        db.add(item)
        db.flush()

    db.commit()
    db.refresh(draft)
    return draft


def _validate_item(db: Session, item: ImportDraftItem, batch: WeeklyBatch | None = None) -> None:
    if item.item_kind == DraftItemKind.UNRESOLVED:
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = None
        return

    if not item.player_name or not item.player_name.strip():
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = "player_name_required"
        return
    if item.item_kind == DraftItemKind.DESIGNATION and item.designation_type is None:
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = "designation_type_required"
        return

    if batch is None:
        draft = db.get(PersistentImportDraft, item.import_draft_id)
        if draft is None:
            raise LookupError("draft_not_found")
        batch = db.get(WeeklyBatch, draft.weekly_batch_id)
        if batch is None:
            raise LookupError("batch_not_found")

    # Clear target performance if wish
    if item.item_kind == DraftItemKind.WISH:
        item.target_performance_id = None

    # Explicit administrator selections win; raw names are only auto-match fallbacks.
    actor = db.get(Actor, item.actor_id) if item.actor_id is not None else None
    if actor is None and item.actor_name_raw:
        actor = db.scalar(select(Actor).where(Actor.display_name == item.actor_name_raw.strip()))
    if actor is None:
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = "actor_not_found"
        return
    item.actor_id = actor.id

    role = db.get(Role, item.role_id) if item.role_id is not None else None
    if role is None and item.role_name_raw:
        role = db.scalar(select(Role).where(Role.name == item.role_name_raw.strip()))
    if role is None:
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = "role_not_found"
        return
    item.role_id = role.id

    # Check actor capability
    cap = db.scalar(
        select(ActorRoleCapability).where(
            ActorRoleCapability.actor_id == item.actor_id,
            ActorRoleCapability.role_id == item.role_id,
        )
    )
    if not cap:
        item.validation_status = DraftValidationStatus.INVALID
        item.failure_reason = "actor_role_capability_missing"
        return

    # Check performance range for designations
    if item.item_kind == DraftItemKind.DESIGNATION and item.target_performance_id is not None:
        perf = db.get(Performance, item.target_performance_id)
        if (
            perf is None
            or perf.theater_id != batch.theater_id
            or not (
                batch.week_start <= perf.performance_date <= batch.week_start + timedelta(days=6)
            )
        ):
            item.validation_status = DraftValidationStatus.INVALID
            item.failure_reason = "performance_outside_batch"
            return

    item.validation_status = DraftValidationStatus.VALID
    item.failure_reason = None


def create_manual_item(db: Session, draft_id: int, payload: DraftItemCreate) -> ImportDraftItem:
    draft = db.get(PersistentImportDraft, draft_id)
    if draft is None:
        raise LookupError("draft_not_found")
    _require_editable_batch(db, draft)

    item = ImportDraftItem(
        import_draft_id=draft_id,
        item_kind=payload.item_kind,
        designation_type=payload.designation_type,
        player_name=payload.player_name,
        actor_name_raw=payload.actor_name_raw,
        role_name_raw=payload.role_name_raw,
        actor_id=payload.actor_id,
        role_id=payload.role_id,
        target_performance_id=payload.target_performance_id,
        note=payload.note,
    )
    db.add(item)
    db.flush()

    _validate_item(db, item)
    has_confirmed = any(
        existing.confirmed_at is not None for existing in draft.items if existing.id != item.id
    )
    draft.status = (
        ImportDraftStatus.PARTIALLY_CONFIRMED if has_confirmed else ImportDraftStatus.DRAFT
    )
    db.commit()
    db.refresh(item)
    return item


def update_draft_item(db: Session, item_id: int, payload: DraftItemUpdate) -> ImportDraftItem:
    item = db.get(ImportDraftItem, item_id)
    if item is None:
        raise LookupError("draft_item_not_found")
    draft = db.get(PersistentImportDraft, item.import_draft_id)
    if draft is None:
        raise LookupError("draft_not_found")
    _require_editable_batch(db, draft)

    # If already confirmed, raise conflict
    if item.confirmed_at is not None:
        raise DraftItemConflict("draft_item_already_confirmed")

    item.item_kind = payload.item_kind
    item.designation_type = payload.designation_type
    item.player_name = payload.player_name
    item.actor_name_raw = payload.actor_name_raw
    item.role_name_raw = payload.role_name_raw
    item.actor_id = payload.actor_id
    item.role_id = payload.role_id
    item.target_performance_id = payload.target_performance_id
    item.note = payload.note

    _validate_item(db, item)
    db.commit()
    db.refresh(item)
    return item


def confirm_draft_item(db: Session, item_id: int) -> ImportDraftItem:
    draft_id = db.scalar(
        select(ImportDraftItem.import_draft_id).where(ImportDraftItem.id == item_id)
    )
    if draft_id is None:
        raise LookupError("draft_item_not_found")
    draft = db.scalar(
        select(PersistentImportDraft)
        .where(PersistentImportDraft.id == draft_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if draft is None:
        raise LookupError("draft_not_found")
    item = db.scalar(
        select(ImportDraftItem)
        .where(ImportDraftItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise LookupError("draft_item_not_found")

    if item.confirmed_at is not None:
        return item

    try:
        batch = _require_editable_batch(db, draft)
        _validate_item(db, item)
        if item.validation_status != DraftValidationStatus.VALID:
            raise DraftItemConflict("draft_item_invalid")

        if item.item_kind == DraftItemKind.DESIGNATION:
            designation = Designation(
                weekly_batch_id=batch.id,
                designation_type=item.designation_type,
                player_name=item.player_name,
                actor_id=item.actor_id,
                role_id=item.role_id,
                target_performance_id=item.target_performance_id,
                submitted_at=utc_now(),
                included_in_batch=True,
                status="confirmed",
            )
            db.add(designation)
            db.flush()
            item.designation_id = designation.id

        elif item.item_kind == DraftItemKind.WISH:
            wish = Wish(
                weekly_batch_id=batch.id,
                player_name=item.player_name,
                actor_id=item.actor_id,
                role_id=item.role_id,
                note=item.note,
            )
            db.add(wish)
            db.flush()
            item.wish_id = wish.id

        item.confirmed_at = utc_now()

        # Update draft aggregate status
        db.flush()
        locked_items = list(
            db.scalars(
                select(ImportDraftItem)
                .where(ImportDraftItem.import_draft_id == draft.id)
                .with_for_update()
            )
        )
        total_items = len(locked_items)
        confirmed_count = sum(
            1 for draft_item in locked_items if draft_item.confirmed_at is not None
        )
        if confirmed_count == total_items:
            draft.status = ImportDraftStatus.CONFIRMED
        elif confirmed_count > 0:
            draft.status = ImportDraftStatus.PARTIALLY_CONFIRMED
        else:
            draft.status = ImportDraftStatus.DRAFT

        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def confirm_valid_items(db: Session, draft_id: int) -> list[dict]:
    draft = db.get(PersistentImportDraft, draft_id)
    if draft is None:
        raise LookupError("draft_not_found")
    _require_editable_batch(db, draft)

    results = []
    # Make a copy of list to prevent iteration issues during DB updates
    items_to_confirm = [
        item
        for item in draft.items
        if item.validation_status == DraftValidationStatus.VALID and item.confirmed_at is None
    ]

    for item in items_to_confirm:
        try:
            confirmed = confirm_draft_item(db, item.id)
            results.append(
                {
                    "item_id": item.id,
                    "success": True,
                    "designation_id": confirmed.designation_id,
                    "wish_id": confirmed.wish_id,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "item_id": item.id,
                    "success": False,
                    "error": str(exc),
                }
            )
    return results


def get_batch_scheduling_inputs(db: Session, batch_id: int) -> dict:
    batch = db.get(WeeklyBatch, batch_id)
    if batch is None:
        raise LookupError("batch_not_found")

    designations = db.scalars(
        select(Designation).where(
            Designation.weekly_batch_id == batch_id,
            Designation.included_in_batch,
        )
    ).all()

    wishes = db.scalars(
        select(Wish).where(
            Wish.weekly_batch_id == batch_id,
        )
    ).all()

    return {
        "designations": [
            {
                "designation_type": d.designation_type,
                "player_name": d.player_name,
                "role_id": d.role_id,
                "actor_id": d.actor_id,
                "target_performance_id": d.target_performance_id,
                "submitted_at": d.submitted_at,
                "failure_reason": d.failure_reason,
            }
            for d in designations
        ],
        "wishes": [
            {
                "player_name": w.player_name,
                "role_id": w.role_id,
                "actor_id": w.actor_id,
                "note": w.note,
            }
            for w in wishes
        ],
    }
