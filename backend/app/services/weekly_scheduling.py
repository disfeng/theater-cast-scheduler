from collections import Counter, defaultdict
import hashlib
import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from app.core.time import utc_now

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    DesignationLifecycleEvent,
    EntitlementItem,
    EntitlementLedgerEntry,
    LeaveRequest,
    LeaveApplication,
    LeaveApplicationDay,
    Performance,
    PerformancePlayer,
    PlayerProfile,
    Role,
    ScheduleAssignment,
    Theater,
    WeeklyBatch,
    Wish,
    WishLifecycleEvent,
)
from app.models.enums import (
    DesignationType,
    EntitlementEventType,
    EntitlementItemStatus,
    LeaveStatus,
    PerformanceStatus,
    RatingLevel,
)
from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot
from app.schemas.weekly_scheduling import (
    AssignmentInput,
    MultiWeekValidationRequest,
    ScheduleMutationRequest,
)
from app.services.rules import consecutive_limit_state, validate_candidate


class ConflictsRequireConfirmation(Exception):
    def __init__(self, conflicts: list[dict[str, object]]) -> None:
        self.conflicts = conflicts


class ScheduleVersionConflict(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version


class IncompletePerformancesError(Exception):
    def __init__(self, performances: list[dict[str, object]]) -> None:
        self.performances = performances


class PredesignationLockedError(Exception):
    def __init__(self, designation_ids: list[int]) -> None:
        self.designation_ids = designation_ids


class UnmetDesignationsRequireConfirmation(Exception):
    def __init__(
        self, designations: list[dict[str, object]], confirmation_token: str, idempotency_key: str
    ) -> None:
        self.designations = designations
        self.confirmation_token = confirmation_token
        self.idempotency_key = idempotency_key


class PublishOperationConflict(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


DESIGNATION_PRIORITY = {
    DesignationType.UNIVERSAL: 300,
    DesignationType.TOP_THREE: 200,
    DesignationType.PAIRED: 100,
}


def _designation_priority(db: Session, row: Designation) -> int:
    item = db.get(EntitlementItem, row.entitlement_item_id) if row.entitlement_item_id else None
    return item.item_type.priority if item else DESIGNATION_PRIORITY[row.designation_type]


def _week_end(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise ValueError("week_start_must_be_monday")
    return week_start + timedelta(days=6)


def _performances(
    db: Session, theater_id: int | None, start: date | None = None, end: date | None = None
) -> list[Performance]:
    statement = (
        select(Performance)
        .where(Performance.status != PerformanceStatus.CANCELLED)
        .options(selectinload(Performance.theater_slot))
        .order_by(Performance.performance_date, Performance.start_time_snapshot, Performance.id)
    )
    if theater_id is not None:
        statement = statement.where(Performance.theater_id == theater_id)
    if start is not None:
        statement = statement.where(Performance.performance_date >= start)
    if end is not None:
        statement = statement.where(Performance.performance_date <= end)
    return list(db.scalars(statement))


def _slot(item: Performance) -> PerformanceSlot:
    return PerformanceSlot(
        item.id,
        item.performance_date,
        item.slot_name_snapshot,
        item.start_time_snapshot,
        item.theater_slot.sort_order if item.theater_slot else 0,
    )


def _actors(db: Session) -> list[Actor]:
    return list(
        db.scalars(select(Actor).options(selectinload(Actor.role_capabilities)).order_by(Actor.id))
    )


def _active_predesignations(db: Session, performance_ids: list[int]) -> list[Designation]:
    if not performance_ids:
        return []
    return list(
        db.scalars(
            select(Designation)
            .where(
                Designation.lifecycle_status == "predesignated",
                Designation.performance_id.in_(performance_ids),
            )
            .order_by(Designation.submitted_at, Designation.id)
        )
    )


def _week_performance_ids_including_cancelled(
    db: Session, theater_id: int, week_start: date
) -> list[int]:
    return list(
        db.scalars(
            select(Performance.id).where(
                Performance.theater_id == theater_id,
                Performance.performance_date >= week_start,
                Performance.performance_date <= _week_end(week_start),
            )
        )
    )


def _get_or_create_locked_batch(db: Session, theater_id: int, week_start: date) -> WeeklyBatch:
    row = db.scalar(
        select(WeeklyBatch)
        .where(WeeklyBatch.theater_id == theater_id, WeeklyBatch.week_start == week_start)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is not None:
        return row
    connection = db.connection()
    driver_connection = getattr(connection.connection, "driver_connection", None)
    if (
        connection.dialect.name == "sqlite"
        and driver_connection is not None
        and not driver_connection.in_transaction
    ):
        # Python's sqlite legacy transaction mode otherwise lets RELEASE SAVEPOINT
        # commit the row, defeating rollback of the surrounding publish operation.
        connection.exec_driver_sql("BEGIN")
    try:
        with db.begin_nested():
            candidate = WeeklyBatch(theater_id=theater_id, week_start=week_start, version=0)
            db.add(candidate)
            db.flush()
        return candidate
    except IntegrityError:
        # The savepoint alone is rolled back. Any durable publish operation or other
        # outer-transaction work remains intact while we lock the unique-key winner.
        for _ in range(3):
            winner = db.scalar(
                select(WeeklyBatch)
                .where(WeeklyBatch.theater_id == theater_id, WeeklyBatch.week_start == week_start)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if winner is not None:
                return winner
        raise ScheduleVersionConflict(0)


def _publish_checkpoint(stage: str) -> None:
    """Deterministic failure-injection seam; production behavior is intentionally empty."""
    return None


def _designation_parties(db: Session, row: Designation) -> tuple[str, str, bool]:
    owner = db.get(PlayerProfile, row.owner_player_id) if row.owner_player_id else None
    beneficiary_record = (
        db.get(PerformancePlayer, row.beneficiary_performance_player_id)
        if row.beneficiary_performance_player_id
        else None
    )
    beneficiary = (
        db.get(PlayerProfile, beneficiary_record.player_profile_id)
        if beneficiary_record and beneficiary_record.player_profile_id
        else None
    )
    fallback = owner is None or beneficiary is None
    return (
        owner.display_name if owner else row.player_name,
        beneficiary.display_name
        if beneficiary
        else (beneficiary_record.player_name_snapshot if beneficiary_record else row.player_name),
        fallback,
    )


def _locked_assignment(db: Session, row: Designation) -> dict[str, object]:
    owner_name, beneficiary_name, legacy_fallback = _designation_parties(db, row)
    item = db.get(EntitlementItem, row.entitlement_item_id) if row.entitlement_item_id else None
    return {
        "performance_id": row.performance_id,
        "role_id": row.role_id,
        "actor_id": row.actor_id,
        "source": "recommended",
        "conflict_codes": [],
        "recommendation_reasons": ["predesignation_locked"],
        "locked": True,
        "designation_id": row.id,
        "designation_type": row.designation_type.value,
        "owner_player_name": owner_name,
        "beneficiary_player_name": beneficiary_name,
        "entitlement_serial": item.serial_number if item else None,
        "legacy_identity_fallback": legacy_fallback,
    }


def _inject_locked(
    db: Session, performance_ids: list[int], assignments: list[dict[str, object]]
) -> list[dict[str, object]]:
    locked = [_locked_assignment(db, row) for row in _active_predesignations(db, performance_ids)]
    keys = {(row["performance_id"], row["role_id"]) for row in locked}
    return [
        row for row in assignments if (row["performance_id"], row["role_id"]) not in keys
    ] + locked


def _assert_locked_unchanged(
    db: Session, performance_ids: list[int], assignments: list[AssignmentInput]
) -> None:
    by_key = {(row.performance_id, row.role_id): row.actor_id for row in assignments}
    changed = [
        row.id
        for row in _active_predesignations(db, performance_ids)
        if by_key.get((row.performance_id, row.role_id)) != row.actor_id
    ]
    if changed:
        raise PredesignationLockedError(changed)


def _validate_assignments(
    db: Session,
    theater_id: int,
    assignments: list[AssignmentInput],
    scope_performances: list[Performance],
    replaced_week_starts: set[date],
    context_assignments: list[AssignmentInput] | None = None,
) -> dict[str, object]:
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    performance_by_id = {item.id: item for item in scope_performances}
    roles = list(
        db.scalars(
            select(Role)
            .where(Role.theater_id == theater_id, Role.is_active.is_(True))
            .order_by(Role.id)
        )
    )
    role_by_id = {item.id: item for item in roles}
    actors = _actors(db)
    actor_by_id = {item.id: item for item in actors}
    keys: set[tuple[int, int]] = set()
    for item in assignments:
        key = (item.performance_id, item.role_id)
        if key in keys:
            raise ValueError("duplicate_assignment_slot")
        keys.add(key)
        if item.performance_id not in performance_by_id:
            raise ValueError("performance_outside_theater_week")
        if item.role_id not in role_by_id:
            raise ValueError("role_outside_theater")
        if item.actor_id not in actor_by_id:
            raise ValueError("actor_not_found")

    timeline_models = _performances(db, None)
    timeline = [_slot(item) for item in timeline_models]
    timeline_by_id = {item.id: item for item in timeline}
    saved_assignments = list(
        db.scalars(
            select(ScheduleAssignment)
            .join(WeeklyBatch, ScheduleAssignment.weekly_batch_id == WeeklyBatch.id)
            .options(selectinload(ScheduleAssignment.performance))
        )
    )
    existing_actor_slots: dict[int, list[PerformanceSlot]] = defaultdict(list)
    monthly_counts: dict[tuple[int, int, int], int] = Counter()
    replaced_batch_ids = (
        set(
            db.scalars(
                select(WeeklyBatch.id).where(
                    WeeklyBatch.theater_id == theater_id,
                    WeeklyBatch.week_start.in_(replaced_week_starts),
                )
            )
        )
        if replaced_week_starts
        else set()
    )
    for assignment in saved_assignments:
        if assignment.weekly_batch_id in replaced_batch_ids:
            continue
        if assignment.performance_id in timeline_by_id:
            existing_actor_slots[assignment.actor_id].append(
                timeline_by_id[assignment.performance_id]
            )
        performance_date = assignment.performance.performance_date
        monthly_counts[(assignment.actor_id, performance_date.year, performance_date.month)] += 1

    capabilities = {actor.id: {cap.role_id for cap in actor.role_capabilities} for actor in actors}
    leave_rows = db.execute(
        select(LeaveRequest.actor_id, LeaveRequest.leave_date).where(
            LeaveRequest.status == LeaveStatus.APPROVED
        )
    ).all()
    leave_rows += db.execute(
        select(LeaveApplication.actor_id, LeaveApplicationDay.leave_date)
        .join(LeaveApplicationDay, LeaveApplicationDay.application_id == LeaveApplication.id)
        .where(
            LeaveApplicationDay.status == LeaveStatus.APPROVED,
            LeaveApplicationDay.withdrawn_at.is_(None),
        )
    ).all()
    approved_leave: dict[int, set[date]] = defaultdict(set)
    for actor_id, leave_date in leave_rows:
        approved_leave[actor_id].add(leave_date)

    conflicts: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    placed: list[AssignmentCandidate] = []
    current_actor_slots = {key: list(value) for key, value in existing_actor_slots.items()}
    current_counts = dict(monthly_counts)
    for item in context_assignments or []:
        performance = timeline_by_id.get(item.performance_id)
        if (
            performance is None
            or next(row.theater_id for row in timeline_models if row.id == item.performance_id)
            != theater_id
        ):
            raise ValueError("context_performance_outside_theater")
        if item.role_id not in role_by_id:
            raise ValueError("context_role_outside_theater")
        if item.actor_id not in actor_by_id:
            raise ValueError("context_actor_not_found")
        current_actor_slots.setdefault(item.actor_id, []).append(performance)
        context_month_key = (item.actor_id, performance.date.year, performance.date.month)
        current_counts[context_month_key] = current_counts.get(context_month_key, 0) + 1
    ordered_assignments = sorted(
        assignments,
        key=lambda item: (
            timeline_by_id[item.performance_id].date,
            timeline_by_id[item.performance_id].start_time,
            timeline_by_id[item.performance_id].sort_order,
            item.performance_id,
            item.role_id,
        ),
    )
    for item in ordered_assignments:
        candidate = AssignmentCandidate(
            item.actor_id, item.role_id, timeline_by_id[item.performance_id]
        )
        actor = actor_by_id[item.actor_id]
        month_key = (
            item.actor_id,
            candidate.performance.date.year,
            candidate.performance.date.month,
        )
        candidate_month_counts = {
            actor_id: count
            for (actor_id, year, month), count in current_counts.items()
            if year == candidate.performance.date.year and month == candidate.performance.date.month
        }
        violations = validate_candidate(
            candidate,
            placed,
            approved_leave,
            capabilities,
            candidate_month_counts,
            {
                row.id: row.low_rating_monthly_cap
                for row in actors
                if row.low_rating_monthly_cap is not None
            },
            {row.id for row in actors if row.rating_level == RatingLevel.SUSPENDED},
        )
        consecutive_state = consecutive_limit_state(
            item.actor_id,
            candidate.performance,
            current_actor_slots,
            actor.max_consecutive_performances,
            ordered_timeline=timeline,
        )
        if consecutive_state == "exceeded":
            from app.schemas.scheduling import RuleViolation

            violations.append(RuleViolation("consecutive_limit_exceeded", "超过演员个人最大连场数"))
        elif consecutive_state == "reached":
            warnings.append(
                {
                    "code": "consecutive_limit_reached",
                    "message": "已达到演员个人最大连场数",
                    "performance_id": item.performance_id,
                    "role_id": item.role_id,
                    "actor_id": item.actor_id,
                }
            )
        for violation in violations:
            conflicts.append(
                {
                    "code": violation.code,
                    "message": violation.message,
                    "performance_id": item.performance_id,
                    "role_id": item.role_id,
                    "actor_id": item.actor_id,
                }
            )
        placed.append(candidate)
        current_actor_slots.setdefault(item.actor_id, []).append(candidate.performance)
        current_counts[month_key] = current_counts.get(month_key, 0) + 1

    empty_slots = [
        {"performance_id": performance.id, "role_id": role.id}
        for performance in scope_performances
        for role in roles
        if (performance.id, role.id) not in keys
    ]
    return {"conflicts": conflicts, "warnings": warnings, "empty_slots": empty_slots}


def validate_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    from app.services.weekly_conflicts import validate_schedule as validator

    return validator(db, payload)


def validate_schedule_context(
    db: Session, payload: MultiWeekValidationRequest
) -> dict[str, object]:
    from app.services.weekly_conflicts import validate_schedule_context as validator

    return validator(db, payload)


def get_workspace(db: Session, theater_id: int, week_start: date) -> dict[str, object]:
    from app.services.weekly_workspace import get_workspace as workspace_reader

    return workspace_reader(db, theater_id, week_start)


def recommend_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    from app.services.weekly_commands import recommend_schedule as recommender

    return recommender(db, payload)


def _canonical_publish_hash(payload: ScheduleMutationRequest) -> str:
    body = {
        "theater_id": payload.theater_id,
        "week_start": payload.week_start.isoformat(),
        "expected_version": payload.expected_version,
        "assignments": sorted(
            [
                {
                    "performance_id": row.performance_id,
                    "role_id": row.role_id,
                    "actor_id": row.actor_id,
                    "source": row.source,
                }
                for row in payload.assignments
            ],
            key=lambda row: (row["performance_id"], row["role_id"], row["actor_id"], row["source"]),
        ),
        "confirm_conflicts": payload.confirm_conflicts,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _specific_unmet_reason(
    db: Session,
    row: Designation,
    invalid: set[tuple[int, int, int]],
    assigned: set[tuple[int, int, int]],
) -> str | None:
    performance = db.get(Performance, row.performance_id)
    actor = db.get(Actor, row.actor_id)
    if performance and performance.status == PerformanceStatus.CANCELLED:
        return "performance_cancelled"
    if actor and actor.rating_level == RatingLevel.SUSPENDED:
        return "actor_suspended"
    if performance and db.scalar(
        select(LeaveRequest.id).where(
            LeaveRequest.actor_id == row.actor_id,
            LeaveRequest.leave_date == performance.performance_date,
            LeaveRequest.status == LeaveStatus.APPROVED,
        )
    ):
        return "actor_on_leave"
    if performance and db.scalar(
        select(LeaveApplicationDay.id)
        .join(LeaveApplication, LeaveApplication.id == LeaveApplicationDay.application_id)
        .where(
            LeaveApplication.actor_id == row.actor_id,
            LeaveApplication.theater_id == performance.theater_id,
            LeaveApplicationDay.leave_date == performance.performance_date,
            LeaveApplicationDay.status == LeaveStatus.APPROVED,
            LeaveApplicationDay.withdrawn_at.is_(None),
        )
    ):
        return "actor_on_leave"
    if not db.scalar(
        select(ActorRoleCapability.actor_id).where(
            ActorRoleCapability.actor_id == row.actor_id, ActorRoleCapability.role_id == row.role_id
        )
    ):
        return "actor_role_capability_missing"
    key = (row.performance_id, row.role_id, row.actor_id)
    if key not in assigned:
        return "predesignation_assignment_missing"
    if key in invalid:
        return "hard_rule_conflict"
    return None


def _unmet_scope(
    db: Session, payload: ScheduleMutationRequest, validation: dict[str, object]
) -> list[dict[str, object]]:
    performance_ids = _week_performance_ids_including_cancelled(
        db, payload.theater_id, payload.week_start
    )
    invalid = {
        (row["performance_id"], row["role_id"], row["actor_id"]) for row in validation["conflicts"]
    }
    assigned = {(row.performance_id, row.role_id, row.actor_id) for row in payload.assignments}
    result = []
    for row in _active_predesignations(db, performance_ids):
        reason = _specific_unmet_reason(db, row, invalid, assigned)
        if reason is None:
            continue
        item = db.get(EntitlementItem, row.entitlement_item_id) if row.entitlement_item_id else None
        owner_name, beneficiary_name, legacy_fallback = _designation_parties(db, row)
        destination = "expired" if item and item.expires_at <= utc_now() else "available"
        result.append(
            {
                "id": row.id,
                "version": row.version,
                "player_name": row.player_name,
                "owner_player_name": owner_name,
                "beneficiary_player_name": beneficiary_name,
                "legacy_identity_fallback": legacy_fallback,
                "performance_id": row.performance_id,
                "role_id": row.role_id,
                "actor_id": row.actor_id,
                "failure_reason": reason,
                "entitlement_item_id": row.entitlement_item_id,
                "entitlement_serial": item.serial_number if item else None,
                "item_current_status": item.status.value if item else None,
                "refund_target": owner_name,
                "refund_status": destination,
            }
        )
    return result


def _scope_hash(scope: list[dict[str, object]]) -> str:
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _reconcile_designations(
    db: Session,
    payload: ScheduleMutationRequest,
    validation: dict[str, object],
    operator_id: int,
    performance_ids: list[int] | None = None,
) -> None:
    performance_ids = performance_ids or _week_performance_ids_including_cancelled(
        db, payload.theater_id, payload.week_start
    )
    rows = list(
        db.scalars(
            select(Designation)
            .where(
                Designation.performance_id.in_(performance_ids),
                Designation.lifecycle_status == "predesignated",
            )
            .order_by(Designation.id)
            .with_for_update()
        )
    )
    assigned = {(row.performance_id, row.role_id, row.actor_id) for row in payload.assignments}
    invalid = {
        (row["performance_id"], row["role_id"], row["actor_id"]) for row in validation["conflicts"]
    }
    now = utc_now()
    for row in rows:
        reason = _specific_unmet_reason(db, row, invalid, assigned)
        effective = reason is None
        item = (
            db.scalar(
                select(EntitlementItem)
                .where(EntitlementItem.id == row.entitlement_item_id)
                .with_for_update()
            )
            if row.entitlement_item_id
            else None
        )
        old_status = row.lifecycle_status
        action = "publish_effective" if effective else "publish_unsatisfied"
        event_key = f"{payload.idempotency_key or payload.week_start}:{row.id}:{action}"
        if db.scalar(
            select(DesignationLifecycleEvent.id).where(
                DesignationLifecycleEvent.designation_id == row.id,
                DesignationLifecycleEvent.action == action,
                DesignationLifecycleEvent.idempotency_key == event_key,
            )
        ):
            continue
        if effective:
            if (
                item
                and item.status == EntitlementItemStatus.RESERVED
                and item.current_designation_id == row.id
            ):
                before = item.status
                item.status = EntitlementItemStatus.CONSUMED
                db.add(
                    EntitlementLedgerEntry(
                        item_id=item.id,
                        event_type=EntitlementEventType.CONSUMED,
                        from_status=before,
                        to_status=item.status,
                        performance_id=row.performance_id,
                        designation_id=row.id,
                        operator_user_id=operator_id,
                        reason="weekly_schedule_published",
                    )
                )
        else:
            if (
                item
                and item.status == EntitlementItemStatus.RESERVED
                and item.current_designation_id == row.id
            ):
                before = item.status
                item.status = (
                    EntitlementItemStatus.EXPIRED
                    if item.expires_at <= now
                    else EntitlementItemStatus.AVAILABLE
                )
                item.current_designation_id = None
                # Expired is the destination state, but this is still explicitly a release/refund event.
                db.add(
                    EntitlementLedgerEntry(
                        item_id=item.id,
                        event_type=EntitlementEventType.RELEASED,
                        from_status=before,
                        to_status=item.status,
                        performance_id=row.performance_id,
                        designation_id=row.id,
                        operator_user_id=operator_id,
                        reason=reason,
                    )
                )
        db.flush()
        _publish_checkpoint("item_and_entitlement_ledger")
        row.lifecycle_status = "effective" if effective else "unsatisfied"
        row.failure_reason = None if effective else reason
        row.version += 1
        snapshot = {
            "designation": {
                "id": row.id,
                "version": row.version,
                "lifecycle_status": row.lifecycle_status,
                "failure_reason": row.failure_reason,
            }
        }
        request_hash = hashlib.sha256(
            json.dumps(
                {"week_start": str(payload.week_start), "action": action}, sort_keys=True
            ).encode()
        ).hexdigest()
        db.add(
            DesignationLifecycleEvent(
                designation_id=row.id,
                operator_user_id=operator_id,
                action=action,
                idempotency_key=event_key,
                request_hash=request_hash,
                result_snapshot=snapshot,
                from_status=old_status,
                to_status=row.lifecycle_status,
                entitlement_item_id=row.entitlement_item_id,
                note=row.failure_reason,
            )
        )
        db.flush()
        _publish_checkpoint("designation_event")


def _reconcile_wishes(
    db: Session,
    payload: ScheduleMutationRequest,
    operator_id: int,
    performance_ids: list[int] | None = None,
) -> None:
    performance_ids = performance_ids or _week_performance_ids_including_cancelled(
        db, payload.theater_id, payload.week_start
    )
    rows = list(
        db.scalars(
            select(Wish)
            .where(Wish.performance_id.in_(performance_ids), Wish.status == "accepted")
            .order_by(Wish.id)
            .with_for_update()
        )
    )
    assigned = {(row.performance_id, row.role_id, row.actor_id) for row in payload.assignments}
    for row in rows:
        effective = (row.performance_id, row.role_id, row.actor_id) in assigned
        action = "publish_effective" if effective else "publish_unsatisfied"
        event_key = f"{payload.idempotency_key or payload.week_start}:{row.id}:{action}"
        if db.scalar(
            select(WishLifecycleEvent.id).where(
                WishLifecycleEvent.action == action,
                WishLifecycleEvent.idempotency_key == event_key,
            )
        ):
            continue
        old_status = row.status
        row.status = "effective" if effective else "unsatisfied"
        row.failure_reason = None if effective else "actor_not_assigned"
        row.version += 1
        request_hash = hashlib.sha256(
            json.dumps(
                {"week_start": str(payload.week_start), "action": action}, sort_keys=True
            ).encode()
        ).hexdigest()
        db.add(
            WishLifecycleEvent(
                wish_id=row.id,
                operator_user_id=operator_id,
                action=action,
                idempotency_key=event_key,
                request_hash=request_hash,
                result_snapshot={
                    "id": row.id,
                    "version": row.version,
                    "status": row.status,
                    "failure_reason": row.failure_reason,
                },
                from_status=old_status,
                to_status=row.status,
                note=row.failure_reason,
            )
        )
    db.flush()


def persist_schedule(
    db: Session, payload: ScheduleMutationRequest, publish: bool, operator_email: str | None = None
) -> dict[str, object]:
    from app.services.weekly_publication import persist_schedule as persister

    return persister(db, payload, publish, operator_email)
