#!/usr/bin/env python3
"""Settle effective designation/wish records for performances whose start time passed."""

import argparse
from datetime import datetime

from sqlalchemy import or_, select

from app.db.session import SessionLocal
from app.models.entities import Designation, Performance, User, Wish
from app.models.enums import UserRole
from app.services.performance_fulfillment import fulfill_ended_performance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", help="Local datetime, for example 2026-07-20T23:00:00")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    with SessionLocal() as db:
        operator = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.id))
        if operator is None:
            raise RuntimeError("admin_operator_not_found")
        candidate_ids = list(
            db.scalars(
                select(Performance.id)
                .where(
                    or_(
                        Performance.id.in_(
                            select(Designation.performance_id).where(
                                Designation.lifecycle_status == "effective"
                            )
                        ),
                        Performance.id.in_(
                            select(Wish.performance_id).where(Wish.status == "effective")
                        ),
                    )
                )
                .order_by(Performance.performance_date, Performance.start_time_snapshot)
            )
        )
        totals = {"performances": 0, "designations": 0, "wishes": 0}
        for performance_id in candidate_ids:
            performance = db.get(Performance, performance_id)
            if datetime.combine(
                performance.performance_date, performance.start_time_snapshot
            ) > now:
                continue
            result = fulfill_ended_performance(
                db,
                performance_id,
                operator.id,
                now=now,
                idempotency_key=f"auto-complete:{performance_id}",
            )
            totals["performances"] += 1
            totals["designations"] += result["designations"]
            totals["wishes"] += result["wishes"]
        db.commit()
        print(
            "完成场次 {performances}，指定 {designations}，许愿 {wishes}".format(**totals)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

