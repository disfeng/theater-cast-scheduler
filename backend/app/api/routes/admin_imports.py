from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import WeeklyBatch, PersistentImportDraft, ImportDraftItem
from app.schemas.admin_imports import (
    BatchSchedulingInputs,
    DraftItemCreate,
    DraftItemRead,
    DraftItemUpdate,
    ImportDraftRead,
    ImportParseRequest,
    WeeklyBatchCreate,
    WeeklyBatchRead,
)
from app.services.admin_imports import (
    DraftItemConflict,
    confirm_draft_item,
    confirm_valid_items,
    create_manual_item,
    get_batch_scheduling_inputs,
    get_or_create_weekly_batch,
    parse_import_draft,
    update_draft_item,
)

router = APIRouter(prefix="/admin", tags=["admin_imports"])


@router.get("/weekly-batches", response_model=list[WeeklyBatchRead])
def get_weekly_batches(
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[WeeklyBatch]:
    return list(db.scalars(select(WeeklyBatch).order_by(WeeklyBatch.id)).all())


@router.post("/weekly-batches", response_model=WeeklyBatchRead)
def post_weekly_batch(
    payload: WeeklyBatchCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WeeklyBatch:
    try:
        return get_or_create_weekly_batch(db, payload.theater_id, payload.week_start)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/weekly-batches/{batch_id}", response_model=WeeklyBatchRead)
def get_weekly_batch(
    batch_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WeeklyBatch:
    batch = db.get(WeeklyBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="batch_not_found")
    return batch


@router.post("/import-drafts/parse", response_model=ImportDraftRead)
def post_import_drafts_parse(
    batch_id: int,
    payload: ImportParseRequest,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PersistentImportDraft:
    try:
        return parse_import_draft(db, batch_id, payload.raw_text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/import-drafts/{draft_id}", response_model=ImportDraftRead)
def get_import_draft(
    draft_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PersistentImportDraft:
    draft = db.get(PersistentImportDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return draft


@router.post("/import-drafts/{draft_id}/items", response_model=DraftItemRead)
def post_manual_item(
    draft_id: int,
    payload: DraftItemCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportDraftItem:
    try:
        return create_manual_item(db, draft_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/import-draft-items/{item_id}", response_model=DraftItemRead)
def patch_draft_item(
    item_id: int,
    payload: DraftItemUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportDraftItem:
    try:
        return update_draft_item(db, item_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftItemConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/import-draft-items/{item_id}/confirm", response_model=DraftItemRead)
def post_confirm_draft_item(
    item_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportDraftItem:
    try:
        return confirm_draft_item(db, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftItemConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/import-drafts/{draft_id}/confirm-valid")
def post_confirm_valid_items(
    draft_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return confirm_valid_items(db, draft_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/weekly-batches/{batch_id}/scheduling-inputs", response_model=BatchSchedulingInputs)
def get_batch_inputs(
    batch_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_batch_scheduling_inputs(db, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
