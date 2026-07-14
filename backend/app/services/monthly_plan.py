from datetime import date, time

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Designation,
    ImportDraftItem,
    Performance,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    TheaterWeeklyTemplateEntry,
)
from app.models.enums import PerformanceStatus
from app.services.calendar import generate_month_performances


class MonthlyPlanConflict(Exception):
    pass


def _ensure_regeneration_is_safe(db: Session, existing: list[Performance]) -> None:
    if any(item.status != PerformanceStatus.DRAFT for item in existing):
        raise MonthlyPlanConflict("monthly_plan_has_non_draft_performances")
    performance_ids = [item.id for item in existing]
    if not performance_ids:
        return
    has_assignment = db.scalar(
        select(ScheduleAssignment.id)
        .where(ScheduleAssignment.performance_id.in_(performance_ids))
        .limit(1)
    )
    has_designation = db.scalar(
        select(Designation.id)
        .where(Designation.target_performance_id.in_(performance_ids))
        .limit(1)
    )
    has_import_draft = db.scalar(
        select(ImportDraftItem.id)
        .where(ImportDraftItem.target_performance_id.in_(performance_ids))
        .limit(1)
    )
    if has_assignment is not None or has_designation is not None or has_import_draft is not None:
        raise MonthlyPlanConflict("monthly_plan_has_referenced_performances")


def replace_monthly_plan(
    db: Session,
    theater_id: int,
    year: int,
    month: int,
    days: dict[date, list[int]],
) -> list[Performance]:
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    if not theater.is_active:
        raise ValueError("theater_inactive")
    if month < 1 or month > 12:
        raise ValueError("invalid_month")
    if any(item.year != year or item.month != month for item in days):
        raise ValueError("performance_date_outside_month")

    requested_slot_ids = {slot_id for slot_ids in days.values() for slot_id in slot_ids}
    slots = {
        slot.id: slot
        for slot in db.scalars(
            select(TheaterSlot).where(
                TheaterSlot.id.in_(requested_slot_ids),
                TheaterSlot.theater_id == theater_id,
                TheaterSlot.is_active.is_(True),
            )
        )
    } if requested_slot_ids else {}
    if set(slots) != requested_slot_ids:
        raise ValueError("invalid_theater_slot")

    existing = list_month_performances(db, theater_id, year, month)
    existing_by_key = {
        (item.performance_date, item.theater_slot_id): item for item in existing
    }
    requested_keys = {
        (performance_date, slot_id)
        for performance_date, slot_ids in days.items()
        for slot_id in slot_ids
    }
    remove = [item for key, item in existing_by_key.items() if key not in requested_keys]
    _ensure_regeneration_is_safe(db, remove)

    try:
        for performance in remove:
            db.delete(performance)
        for performance_date, slot_id in requested_keys - existing_by_key.keys():
            slot = slots[slot_id]
            db.add(
                Performance(
                    theater_id=theater_id,
                    theater_slot_id=slot.id,
                    performance_date=performance_date,
                    slot_name_snapshot=slot.name,
                    start_time_snapshot=slot.start_time,
                    status=PerformanceStatus.DRAFT,
                )
            )
        db.commit()
        return list_month_performances(db, theater_id, year, month)
    except Exception:
        db.rollback()
        raise


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
    if not theater.is_active:
        raise ValueError("theater_inactive")

    existing = db.scalars(
        select(Performance).where(
            Performance.theater_id == theater_id,
            extract("year", Performance.performance_date) == year,
            extract("month", Performance.performance_date) == month,
        )
    ).all()

    _ensure_regeneration_is_safe(db, list(existing))

    try:
        for performance in existing:
            db.delete(performance)
        db.flush()

        entries = db.scalars(select(TheaterWeeklyTemplateEntry).where(TheaterWeeklyTemplateEntry.theater_id == theater_id)).all()
        slots = {slot.id: slot for slot in db.scalars(select(TheaterSlot).where(TheaterSlot.theater_id == theater_id, TheaterSlot.is_active.is_(True))).all()}
        template: dict[str, list[tuple[int, str, time]]] = {}
        for entry in entries:
            slot = slots.get(entry.theater_slot_id)
            if slot is not None: template.setdefault(entry.weekday, []).append((slot.id, slot.name, slot.start_time))
        for values in template.values(): values.sort(key=lambda item: item[2])
        drafts = generate_month_performances(year, month, template, closed_dates)
        performances = [
            Performance(
                theater_id=theater_id,
                performance_date=draft.date,
                theater_slot_id=draft.theater_slot_id,
                slot_name_snapshot=draft.slot_name,
                start_time_snapshot=draft.start_time,
                status=PerformanceStatus.DRAFT,
            )
            for draft in drafts
        ]
        db.add_all(performances)
        db.commit()
        for performance in performances:
            db.refresh(performance)
        return performances
    except Exception:
        db.rollback()
        raise


def list_month_performances(
    db: Session, theater_id: int, year: int, month: int
) -> list[Performance]:
    statement = (
        select(Performance)
        .where(
            Performance.theater_id == theater_id,
            extract("year", Performance.performance_date) == year,
            extract("month", Performance.performance_date) == month,
        )
        .order_by(Performance.performance_date, Performance.start_time_snapshot, Performance.id)
    )
    return list(db.scalars(statement))
