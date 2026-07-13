from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.models.entities import Performance, Theater, Designation, ScheduleAssignment
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
    if has_assignment is not None or has_designation is not None:
        raise MonthlyPlanConflict("monthly_plan_has_referenced_performances")


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

    _ensure_regeneration_is_safe(db, list(existing))

    try:
        for performance in existing:
            db.delete(performance)
        db.flush()

        drafts = generate_month_performances(
            year, month, theater.default_weekly_template, closed_dates
        )
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
        .order_by(Performance.performance_date, Performance.slot)
    )
    return list(db.scalars(statement))
