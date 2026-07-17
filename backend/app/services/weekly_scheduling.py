from collections import Counter, defaultdict
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import delete, false, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from fastapi.encoders import jsonable_encoder

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    DesignationLifecycleEvent,
    EntitlementItem,
    EntitlementLedgerEntry,
    LeaveRequest,
    Performance,
    PerformancePlayer,
    PlayerProfile,
    Role,
    ScheduleAssignment,
    Theater,
    User,
    WeeklyBatch,
    WeeklyPublishOperation,
    Wish,
)
from app.models.enums import (
    BatchStatus,
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
    DesignationType.UNIVERSAL: 0,
    DesignationType.TOP_THREE: 1,
    DesignationType.PAIRED: 2,
}


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
    end = _week_end(payload.week_start)
    week_performances = _performances(db, payload.theater_id, payload.week_start, end)
    context_week_starts = {week.week_start for week in payload.context_weeks}
    if payload.week_start in context_week_starts or len(context_week_starts) != len(
        payload.context_weeks
    ):
        raise ValueError("duplicate_week_context")
    return _validate_assignments(
        db,
        payload.theater_id,
        payload.assignments,
        week_performances,
        {payload.week_start, *context_week_starts},
        [assignment for week in payload.context_weeks for assignment in week.assignments],
    )


def validate_schedule_context(
    db: Session, payload: MultiWeekValidationRequest
) -> dict[str, object]:
    week_starts = [week.week_start for week in payload.weeks]
    if len(week_starts) != len(set(week_starts)):
        raise ValueError("duplicate_week_context")
    scope_performances: list[Performance] = []
    assignments: list[AssignmentInput] = []
    for week in payload.weeks:
        scope_performances.extend(
            _performances(
                db,
                payload.theater_id,
                week.week_start,
                _week_end(week.week_start),
            )
        )
        assignments.extend(week.assignments)
    return _validate_assignments(
        db,
        payload.theater_id,
        assignments,
        scope_performances,
        set(week_starts),
    )


def get_workspace(db: Session, theater_id: int, week_start: date) -> dict[str, object]:
    end = _week_end(week_start)
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    performances = _performances(db, theater_id, week_start, end)
    roles = list(
        db.scalars(
            select(Role)
            .where(Role.theater_id == theater_id, Role.is_active.is_(True))
            .order_by(Role.id)
        )
    )
    actors = _actors(db)
    batch = db.scalar(
        select(WeeklyBatch)
        .where(WeeklyBatch.theater_id == theater_id, WeeklyBatch.week_start == week_start)
        .options(selectinload(WeeklyBatch.assignments))
    )
    assignments = list(batch.assignments) if batch else []
    request = ScheduleMutationRequest(
        theater_id=theater_id,
        week_start=week_start,
        expected_version=batch.version if batch else 0,
        assignments=[
            AssignmentInput(
                performance_id=row.performance_id,
                role_id=row.role_id,
                actor_id=row.actor_id,
                source=row.source,
            )
            for row in assignments
        ],
        confirm_conflicts=True,
    )
    validation = validate_schedule(db, request)
    summary = dict(Counter(item["code"] for item in validation["conflicts"]))
    warning_summary = dict(Counter(item["code"] for item in validation["warnings"]))
    week_counts = Counter(row.actor_id for row in assignments)
    role_ids = {role.id for role in roles}
    performance_ids = [row.id for row in performances]
    unmet_rows = (
        list(
            db.scalars(
                select(Designation).where(
                    Designation.performance_id.in_(performance_ids),
                    Designation.lifecycle_status == "unsatisfied",
                )
            )
        )
        if performance_ids
        else []
    )
    serialized_assignments = _inject_locked(
        db,
        [row.id for row in performances],
        [
            {
                "performance_id": row.performance_id,
                "role_id": row.role_id,
                "actor_id": row.actor_id,
                "source": row.source,
                "conflict_codes": row.conflict_codes,
            }
            for row in assignments
        ],
    )
    return {
        "theater_id": theater_id,
        "week_start": week_start,
        "week_end": end,
        "batch_id": batch.id if batch else None,
        "status": batch.status.value if batch else "uncreated",
        "version": batch.version if batch else 0,
        "updated_at": batch.updated_at if batch else None,
        "published_at": batch.published_at if batch else None,
        "performances": [
            {
                "id": row.id,
                "performance_date": row.performance_date,
                "slot_name": row.slot_name_snapshot,
                "start_time": row.start_time_snapshot,
                "sort_order": row.theater_slot.sort_order if row.theater_slot else 0,
            }
            for row in performances
        ],
        "roles": [{"id": row.id, "name": row.name, "group_name": row.group_name} for row in roles],
        "actors": [
            {
                "id": row.id,
                "display_name": row.display_name,
                "rating_level": row.rating_level.value,
                "max_consecutive_performances": row.max_consecutive_performances,
                "low_rating_monthly_cap": row.low_rating_monthly_cap,
                "role_ids": [
                    cap.role_id for cap in row.role_capabilities if cap.role_id in role_ids
                ],
                "weekly_count": week_counts[row.id],
                "monthly_count": 0,
            }
            for row in actors
        ],
        "assignments": serialized_assignments,
        "conflicts": validation["conflicts"],
        "conflict_summary": summary,
        "warnings": validation["warnings"],
        "warning_summary": warning_summary,
        "empty_slots": validation["empty_slots"],
        "unsatisfied_designations": [
            {
                "id": row.id,
                "player_name": row.player_name,
                "role_id": row.role_id,
                "actor_id": row.actor_id,
                "performance_id": row.performance_id,
                "failure_reason": row.failure_reason,
                "refund_status": "released",
                "refund_target": _designation_parties(db, row)[0],
                "legacy_identity_fallback": _designation_parties(db, row)[2],
            }
            for row in unmet_rows
        ],
        "unsatisfied_wishes": [],
    }


def recommend_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    workspace = get_workspace(db, payload.theater_id, payload.week_start)
    performance_ids = [row["id"] for row in workspace["performances"]]
    injected = _inject_locked(
        db, performance_ids, [row.model_dump() for row in payload.assignments]
    )
    assignments = [AssignmentInput.model_validate(row) for row in injected]
    validation = validate_schedule(db, payload.model_copy(update={"assignments": assignments}))
    batch_id = workspace["batch_id"]
    designations = list(
        db.scalars(
            select(Designation)
            .where(
                ((Designation.weekly_batch_id == batch_id) if batch_id else false())
                | (
                    (Designation.performance_id.in_(performance_ids))
                    & (Designation.lifecycle_status == "predesignated")
                )
            )
            .order_by(Designation.submitted_at, Designation.id)
        )
    )
    wishes = list(
        db.scalars(
            select(Wish)
            .where(
                (
                    ((Wish.weekly_batch_id == batch_id) if batch_id else false())
                    | Wish.performance_id.in_(performance_ids)
                ),
                ((Wish.status.is_(None)) | (Wish.status.in_(["active", "accepted"]))),
            )
            .order_by(Wish.id)
        )
    )
    sorted_designations = sorted(
        designations,
        key=lambda row: (DESIGNATION_PRIORITY[row.designation_type], row.submitted_at, row.id),
    )
    fulfilled_designation_ids = {
        designation.id
        for designation in sorted_designations
        if any(
            row.role_id == designation.role_id
            and row.actor_id == designation.actor_id
            and (
                designation.target_performance_id is None
                or row.performance_id == designation.target_performance_id
            )
            for row in assignments
        )
    }

    def matching_designation(
        actor_id: int, role_id: int, performance_id: int
    ) -> Designation | None:
        return next(
            (
                row
                for row in sorted_designations
                if row.id not in fulfilled_designation_ids
                and row.actor_id == actor_id
                and row.role_id == role_id
                and (
                    row.target_performance_id is None or row.target_performance_id == performance_id
                )
            ),
            None,
        )

    def slot_priority(slot: dict[str, int]) -> tuple[int, int, int]:
        matches = [
            DESIGNATION_PRIORITY[row.designation_type]
            for row in sorted_designations
            if row.id not in fulfilled_designation_ids
            and row.role_id == slot["role_id"]
            and (
                row.target_performance_id is None
                or row.target_performance_id == slot["performance_id"]
            )
        ]
        return (min(matches, default=99), slot["performance_id"], slot["role_id"])

    for slot in sorted(validation["empty_slots"], key=slot_priority):
        candidates = [
            row
            for row in workspace["actors"]
            if slot["role_id"] in row["role_ids"] and row["rating_level"] != "suspended"
        ]
        candidates.sort(
            key=lambda actor: (
                DESIGNATION_PRIORITY[
                    matching_designation(
                        actor["id"], slot["role_id"], slot["performance_id"]
                    ).designation_type
                ]
                if matching_designation(actor["id"], slot["role_id"], slot["performance_id"])
                else 99,
                0
                if any(
                    wish.actor_id == actor["id"]
                    and wish.role_id == slot["role_id"]
                    and (
                        wish.performance_id is None or wish.performance_id == slot["performance_id"]
                    )
                    for wish in wishes
                )
                else 1,
                actor["weekly_count"],
                actor["id"],
            )
        )
        for actor in candidates:
            proposal = AssignmentInput(**slot, actor_id=actor["id"], source="recommended")
            candidate_payload = payload.model_copy(update={"assignments": [*assignments, proposal]})
            candidate_validation = validate_schedule(db, candidate_payload)
            cell_conflicts = [
                item
                for item in candidate_validation["conflicts"]
                if item["performance_id"] == proposal.performance_id
                and item["role_id"] == proposal.role_id
            ]
            if not cell_conflicts:
                assignments.append(proposal)
                actor["weekly_count"] += 1
                designation = matching_designation(
                    actor["id"], slot["role_id"], slot["performance_id"]
                )
                if designation:
                    fulfilled_designation_ids.add(designation.id)
                break
    result_payload = payload.model_copy(update={"assignments": assignments})
    result_validation = validate_schedule(db, result_payload)
    unsatisfied_designations = [
        {
            "id": row.id,
            "player_name": row.player_name,
            "role_id": row.role_id,
            "actor_id": row.actor_id,
            "target_performance_id": row.target_performance_id,
            "failure_reason": "没有符合硬规则的可用槽位",
        }
        for row in sorted_designations
        if row.id not in fulfilled_designation_ids
    ]
    unsatisfied_wishes = [
        {
            "id": row.id,
            "player_name": row.player_name,
            "role_id": row.role_id,
            "actor_id": row.actor_id,
            "performance_id": row.performance_id,
            "performance_player_id": row.performance_player_id,
            "failure_reason": "hard_rules_or_higher_priority_assignment",
        }
        for row in wishes
        if not any(
            assignment.role_id == row.role_id
            and assignment.actor_id == row.actor_id
            and (row.performance_id is None or assignment.performance_id == row.performance_id)
            for assignment in assignments
        )
    ]
    return {
        **workspace,
        "assignments": _inject_locked(
            db,
            performance_ids,
            [
                row.model_dump()
                | {
                    "conflict_codes": [],
                    "recommendation_reasons": (
                        ["performance_scoped_wish"]
                        if any(
                            w.actor_id == row.actor_id
                            and w.role_id == row.role_id
                            and (w.performance_id is None or w.performance_id == row.performance_id)
                            for w in wishes
                        )
                        else ["workload_balance"]
                    ),
                }
                for row in assignments
            ],
        ),
        "conflicts": result_validation["conflicts"],
        "conflict_summary": dict(Counter(item["code"] for item in result_validation["conflicts"])),
        "warnings": result_validation["warnings"],
        "warning_summary": dict(Counter(item["code"] for item in result_validation["warnings"])),
        "empty_slots": result_validation["empty_slots"],
        "unsatisfied_designations": unsatisfied_designations,
        "unsatisfied_wishes": unsatisfied_wishes,
    }


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
        destination = "expired" if item and item.expires_at <= datetime.utcnow() else "available"
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
    db: Session, payload: ScheduleMutationRequest, validation: dict[str, object], operator_id: int
) -> None:
    performance_ids = _week_performance_ids_including_cancelled(
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
    now = datetime.utcnow()
    for row in rows:
        reason = _specific_unmet_reason(db, row, invalid, assigned)
        fulfilled = reason is None
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
        action = "publish_fulfill" if fulfilled else "publish_unsatisfied"
        event_key = f"{payload.idempotency_key or payload.week_start}:{row.id}:{action}"
        if db.scalar(
            select(DesignationLifecycleEvent.id).where(
                DesignationLifecycleEvent.designation_id == row.id,
                DesignationLifecycleEvent.action == action,
                DesignationLifecycleEvent.idempotency_key == event_key,
            )
        ):
            continue
        if fulfilled:
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
        row.lifecycle_status = "fulfilled" if fulfilled else "unsatisfied"
        row.failure_reason = None if fulfilled else reason
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


def persist_schedule(
    db: Session, payload: ScheduleMutationRequest, publish: bool, operator_email: str | None = None
) -> dict[str, object]:
    week_performances = _performances(
        db, payload.theater_id, payload.week_start, _week_end(payload.week_start)
    )
    _assert_locked_unchanged(db, [row.id for row in week_performances], payload.assignments)
    validation = validate_schedule(db, payload)
    if publish:
        active_role_ids = set(
            db.scalars(
                select(Role.id).where(
                    Role.theater_id == payload.theater_id,
                    Role.is_active.is_(True),
                )
            )
        )
        assigned_roles: dict[int, set[int]] = defaultdict(set)
        for assignment in payload.assignments:
            assigned_roles[assignment.performance_id].add(assignment.role_id)
        incomplete = [
            {
                "performance_id": performance.id,
                "missing_role_ids": sorted(
                    active_role_ids - assigned_roles.get(performance.id, set())
                ),
            }
            for performance in week_performances
            if assigned_roles.get(performance.id, set()) != active_role_ids
        ]
        if incomplete:
            raise IncompletePerformancesError(incomplete)
    if validation["conflicts"] and not payload.confirm_conflicts:
        raise ConflictsRequireConfirmation(validation["conflicts"])
    batch = db.scalar(
        select(WeeklyBatch)
        .where(
            WeeklyBatch.theater_id == payload.theater_id,
            WeeklyBatch.week_start == payload.week_start,
        )
        .with_for_update()
    )
    current_version = batch.version if batch else 0
    operator = None
    operation = None
    request_hash = None
    unmet: list[dict[str, object]] = []
    if publish:
        if not payload.idempotency_key:
            payload = payload.model_copy(update={"idempotency_key": secrets.token_urlsafe(24)})
        operator = (
            db.scalar(select(User).where(User.email == operator_email))
            if operator_email
            else db.scalar(select(User).order_by(User.id))
        )
        if operator is None:
            raise LookupError("operator_user_not_found")
        request_hash = _canonical_publish_hash(payload)
        operation = db.scalar(
            select(WeeklyPublishOperation)
            .where(WeeklyPublishOperation.idempotency_key == payload.idempotency_key)
            .with_for_update()
        )
        if operation:
            if (
                operation.theater_id != payload.theater_id
                or operation.week_start != payload.week_start
            ):
                raise PublishOperationConflict("publish_idempotency_scope_conflict")
            if operation.operator_user_id != operator.id:
                raise PublishOperationConflict("publish_idempotency_operator_conflict")
            if operation.request_hash != request_hash:
                raise PublishOperationConflict("publish_idempotency_hash_conflict")
            if operation.status == "completed":
                return operation.response_snapshot
    if payload.expected_version is not None and payload.expected_version != current_version:
        raise ScheduleVersionConflict(current_version)
    if publish:
        unmet = _unmet_scope(db, payload, validation)
        if unmet:
            current_scope_hash = _scope_hash(unmet)
            if operation is None:
                operation = WeeklyPublishOperation(
                    idempotency_key=payload.idempotency_key,
                    theater_id=payload.theater_id,
                    week_start=payload.week_start,
                    weekly_batch_id=batch.id if batch else None,
                    operator_user_id=operator.id,
                    request_hash=request_hash,
                    status="pending_confirmation",
                    confirmation_token=secrets.token_urlsafe(32),
                    unmet_scope_hash=current_scope_hash,
                    unmet_scope=unmet,
                )
                db.add(operation)
                db.commit()
                raise UnmetDesignationsRequireConfirmation(
                    unmet, operation.confirmation_token, payload.idempotency_key
                )
            if (
                operation.status != "pending_confirmation"
                or payload.confirmation_token != operation.confirmation_token
            ):
                raise PublishOperationConflict("publish_confirmation_token_required")
            if operation.unmet_scope_hash != current_scope_hash or operation.unmet_scope != unmet:
                raise PublishOperationConflict("stale_confirmation")
        elif operation and operation.status == "pending_confirmation":
            raise PublishOperationConflict("stale_confirmation")
    if batch is None:
        batch = _get_or_create_locked_batch(db, payload.theater_id, payload.week_start)
        current_version = batch.version
        if payload.expected_version is not None and payload.expected_version != current_version:
            raise ScheduleVersionConflict(current_version)
    if publish and operation is None:
        operation = WeeklyPublishOperation(
            idempotency_key=payload.idempotency_key,
            theater_id=payload.theater_id,
            week_start=payload.week_start,
            weekly_batch_id=batch.id,
            operator_user_id=operator.id,
            request_hash=request_hash,
            status="processing",
        )
        db.add(operation)
        db.flush()
    elif publish:
        operation.weekly_batch_id = batch.id
        operation.status = "processing"
    db.execute(delete(ScheduleAssignment).where(ScheduleAssignment.weekly_batch_id == batch.id))
    conflict_codes: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for conflict in validation["conflicts"]:
        conflict_codes[
            (conflict["performance_id"], conflict["role_id"], conflict["actor_id"])
        ].append(conflict["code"])
    for row in payload.assignments:
        codes = conflict_codes[(row.performance_id, row.role_id, row.actor_id)]
        db.add(
            ScheduleAssignment(
                weekly_batch_id=batch.id,
                performance_id=row.performance_id,
                role_id=row.role_id,
                actor_id=row.actor_id,
                source=row.source,
                conflict_codes=codes,
                requires_approval=bool(codes),
                approved=bool(codes and payload.confirm_conflicts),
            )
        )
    db.flush()
    _publish_checkpoint("assignments")
    batch.version = current_version + 1
    batch.updated_at = datetime.utcnow()
    batch.status = BatchStatus.SCHEDULED if publish else BatchStatus.READY
    batch.published_at = datetime.utcnow() if publish else None
    if publish:
        _reconcile_designations(db, payload, validation, operator.id)
        db.flush()
        result = get_workspace(db, payload.theater_id, payload.week_start)
        operation.status = "completed"
        operation.response_snapshot = jsonable_encoder(result)
        operation.completed_at = datetime.utcnow()
        db.flush()
        _publish_checkpoint("operation_snapshot")
    db.commit()
    return (
        operation.response_snapshot
        if publish
        else get_workspace(db, payload.theater_id, payload.week_start)
    )
