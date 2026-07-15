from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Actor,
    Designation,
    LeaveRequest,
    Performance,
    Role,
    ScheduleAssignment,
    Theater,
    WeeklyBatch,
    Wish,
)
from app.models.enums import BatchStatus, DesignationType, LeaveStatus, PerformanceStatus, RatingLevel
from app.schemas.scheduling import AssignmentCandidate, PerformanceSlot
from app.schemas.weekly_scheduling import AssignmentInput, ScheduleMutationRequest
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


DESIGNATION_PRIORITY = {
    DesignationType.UNIVERSAL: 0,
    DesignationType.TOP_THREE: 1,
    DesignationType.PAIRED: 2,
}


def _week_end(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise ValueError("week_start_must_be_monday")
    return week_start + timedelta(days=6)


def _performances(db: Session, theater_id: int, start: date | None = None, end: date | None = None) -> list[Performance]:
    statement = (
        select(Performance)
        .where(Performance.theater_id == theater_id, Performance.status != PerformanceStatus.CANCELLED)
        .options(selectinload(Performance.theater_slot))
        .order_by(Performance.performance_date, Performance.start_time_snapshot, Performance.id)
    )
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
    return list(db.scalars(select(Actor).options(selectinload(Actor.role_capabilities)).order_by(Actor.id)))


def validate_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    end = _week_end(payload.week_start)
    theater = db.get(Theater, payload.theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    week_performances = _performances(db, payload.theater_id, payload.week_start, end)
    performance_by_id = {item.id: item for item in week_performances}
    roles = list(db.scalars(select(Role).where(Role.theater_id == payload.theater_id, Role.is_active.is_(True)).order_by(Role.id)))
    role_by_id = {item.id: item for item in roles}
    actors = _actors(db)
    actor_by_id = {item.id: item for item in actors}
    keys: set[tuple[int, int]] = set()
    for item in payload.assignments:
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

    timeline_models = _performances(db, payload.theater_id)
    timeline = [_slot(item) for item in timeline_models]
    timeline_by_id = {item.id: item for item in timeline}
    saved_assignments = list(db.scalars(
        select(ScheduleAssignment)
        .join(WeeklyBatch, ScheduleAssignment.weekly_batch_id == WeeklyBatch.id)
        .options(selectinload(ScheduleAssignment.performance))
    ))
    existing_actor_slots: dict[int, list[PerformanceSlot]] = defaultdict(list)
    monthly_counts: dict[tuple[int, int, int], int] = Counter()
    current_batch = db.scalar(select(WeeklyBatch).where(WeeklyBatch.theater_id == payload.theater_id, WeeklyBatch.week_start == payload.week_start))
    for assignment in saved_assignments:
        if current_batch and assignment.weekly_batch_id == current_batch.id:
            continue
        if assignment.performance_id in timeline_by_id:
            existing_actor_slots[assignment.actor_id].append(timeline_by_id[assignment.performance_id])
        performance_date = assignment.performance.performance_date
        monthly_counts[(assignment.actor_id, performance_date.year, performance_date.month)] += 1

    capabilities = {
        actor.id: {cap.role_id for cap in actor.role_capabilities}
        for actor in actors
    }
    leave_rows = db.execute(
        select(LeaveRequest.actor_id, LeaveRequest.leave_date)
        .where(LeaveRequest.status == LeaveStatus.APPROVED)
    ).all()
    approved_leave: dict[int, set[date]] = defaultdict(set)
    for actor_id, leave_date in leave_rows:
        approved_leave[actor_id].add(leave_date)

    conflicts: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    placed: list[AssignmentCandidate] = []
    current_actor_slots = {key: list(value) for key, value in existing_actor_slots.items()}
    current_counts = dict(monthly_counts)
    for item in payload.assignments:
        candidate = AssignmentCandidate(item.actor_id, item.role_id, timeline_by_id[item.performance_id])
        actor = actor_by_id[item.actor_id]
        month_key = (item.actor_id, candidate.performance.date.year, candidate.performance.date.month)
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
            {row.id: row.low_rating_monthly_cap for row in actors if row.low_rating_monthly_cap is not None},
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
            warnings.append({
                "code": "consecutive_limit_reached",
                "message": "已达到演员个人最大连场数",
                "performance_id": item.performance_id,
                "role_id": item.role_id,
                "actor_id": item.actor_id,
            })
        for violation in violations:
            conflicts.append({
                "code": violation.code,
                "message": violation.message,
                "performance_id": item.performance_id,
                "role_id": item.role_id,
                "actor_id": item.actor_id,
            })
        placed.append(candidate)
        current_actor_slots.setdefault(item.actor_id, []).append(candidate.performance)
        current_counts[month_key] = current_counts.get(month_key, 0) + 1

    empty_slots = [
        {"performance_id": performance.id, "role_id": role.id}
        for performance in week_performances for role in roles
        if (performance.id, role.id) not in keys
    ]
    return {"conflicts": conflicts, "warnings": warnings, "empty_slots": empty_slots}


def get_workspace(db: Session, theater_id: int, week_start: date) -> dict[str, object]:
    end = _week_end(week_start)
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    performances = _performances(db, theater_id, week_start, end)
    roles = list(db.scalars(select(Role).where(Role.theater_id == theater_id, Role.is_active.is_(True)).order_by(Role.id)))
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
        assignments=[AssignmentInput(performance_id=row.performance_id, role_id=row.role_id, actor_id=row.actor_id, source=row.source) for row in assignments],
        confirm_conflicts=True,
    )
    validation = validate_schedule(db, request)
    summary = dict(Counter(item["code"] for item in validation["conflicts"]))
    warning_summary = dict(Counter(item["code"] for item in validation["warnings"]))
    week_counts = Counter(row.actor_id for row in assignments)
    role_ids = {role.id for role in roles}
    return {
        "theater_id": theater_id,
        "week_start": week_start,
        "week_end": end,
        "batch_id": batch.id if batch else None,
        "status": batch.status.value if batch else "uncreated",
        "version": batch.version if batch else 0,
        "updated_at": batch.updated_at if batch else None,
        "published_at": batch.published_at if batch else None,
        "performances": [{
            "id": row.id, "performance_date": row.performance_date,
            "slot_name": row.slot_name_snapshot, "start_time": row.start_time_snapshot,
            "sort_order": row.theater_slot.sort_order if row.theater_slot else 0,
        } for row in performances],
        "roles": [{"id": row.id, "name": row.name, "group_name": row.group_name} for row in roles],
        "actors": [{
            "id": row.id, "display_name": row.display_name, "rating_level": row.rating_level.value,
            "max_consecutive_performances": row.max_consecutive_performances,
            "low_rating_monthly_cap": row.low_rating_monthly_cap,
            "role_ids": [cap.role_id for cap in row.role_capabilities if cap.role_id in role_ids],
            "weekly_count": week_counts[row.id], "monthly_count": 0,
        } for row in actors],
        "assignments": [{
            "performance_id": row.performance_id, "role_id": row.role_id, "actor_id": row.actor_id,
            "source": row.source, "conflict_codes": row.conflict_codes,
        } for row in assignments],
        "conflicts": validation["conflicts"],
        "conflict_summary": summary,
        "warnings": validation["warnings"],
        "warning_summary": warning_summary,
        "empty_slots": validation["empty_slots"],
        "unsatisfied_designations": [],
        "unsatisfied_wishes": [],
    }


def recommend_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    validation = validate_schedule(db, payload)
    workspace = get_workspace(db, payload.theater_id, payload.week_start)
    assignments = list(payload.assignments)
    batch_id = workspace["batch_id"]
    designations = list(db.scalars(
        select(Designation)
        .where(Designation.weekly_batch_id == batch_id)
        .order_by(Designation.submitted_at, Designation.id)
    )) if batch_id else []
    wishes = list(db.scalars(
        select(Wish).where(Wish.weekly_batch_id == batch_id).order_by(Wish.id)
    )) if batch_id else []
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
            and (designation.target_performance_id is None or row.performance_id == designation.target_performance_id)
            for row in assignments
        )
    }

    def matching_designation(actor_id: int, role_id: int, performance_id: int) -> Designation | None:
        return next((
            row for row in sorted_designations
            if row.id not in fulfilled_designation_ids
            and row.actor_id == actor_id
            and row.role_id == role_id
            and (row.target_performance_id is None or row.target_performance_id == performance_id)
        ), None)

    def slot_priority(slot: dict[str, int]) -> tuple[int, int, int]:
        matches = [
            DESIGNATION_PRIORITY[row.designation_type]
            for row in sorted_designations
            if row.id not in fulfilled_designation_ids
            and row.role_id == slot["role_id"]
            and (row.target_performance_id is None or row.target_performance_id == slot["performance_id"])
        ]
        return (min(matches, default=99), slot["performance_id"], slot["role_id"])

    for slot in sorted(validation["empty_slots"], key=slot_priority):
        candidates = [row for row in workspace["actors"] if slot["role_id"] in row["role_ids"] and row["rating_level"] != "suspended"]
        candidates.sort(key=lambda actor: (
            DESIGNATION_PRIORITY[matching_designation(actor["id"], slot["role_id"], slot["performance_id"]).designation_type]
            if matching_designation(actor["id"], slot["role_id"], slot["performance_id"])
            else 99,
            0 if any(wish.actor_id == actor["id"] and wish.role_id == slot["role_id"] for wish in wishes) else 1,
            actor["weekly_count"],
            actor["id"],
        ))
        for actor in candidates:
            proposal = AssignmentInput(**slot, actor_id=actor["id"], source="recommended")
            candidate_payload = payload.model_copy(update={"assignments": [*assignments, proposal]})
            candidate_validation = validate_schedule(db, candidate_payload)
            cell_conflicts = [item for item in candidate_validation["conflicts"] if item["performance_id"] == proposal.performance_id and item["role_id"] == proposal.role_id]
            if not cell_conflicts:
                assignments.append(proposal)
                actor["weekly_count"] += 1
                designation = matching_designation(actor["id"], slot["role_id"], slot["performance_id"])
                if designation:
                    fulfilled_designation_ids.add(designation.id)
                break
    result_payload = payload.model_copy(update={"assignments": assignments})
    result_validation = validate_schedule(db, result_payload)
    unsatisfied_designations = [{
        "id": row.id,
        "player_name": row.player_name,
        "role_id": row.role_id,
        "actor_id": row.actor_id,
        "target_performance_id": row.target_performance_id,
        "failure_reason": "没有符合硬规则的可用槽位",
    } for row in sorted_designations if row.id not in fulfilled_designation_ids]
    unsatisfied_wishes = [{
        "id": row.id,
        "player_name": row.player_name,
        "role_id": row.role_id,
        "actor_id": row.actor_id,
    } for row in wishes if not any(
        assignment.role_id == row.role_id and assignment.actor_id == row.actor_id
        for assignment in assignments
    )]
    return {
        **workspace,
        "assignments": [row.model_dump() | {"conflict_codes": []} for row in assignments],
        "conflicts": result_validation["conflicts"],
        "conflict_summary": dict(Counter(item["code"] for item in result_validation["conflicts"])),
        "warnings": result_validation["warnings"],
        "warning_summary": dict(Counter(item["code"] for item in result_validation["warnings"])),
        "empty_slots": result_validation["empty_slots"],
        "unsatisfied_designations": unsatisfied_designations,
        "unsatisfied_wishes": unsatisfied_wishes,
    }


def persist_schedule(db: Session, payload: ScheduleMutationRequest, publish: bool) -> dict[str, object]:
    validation = validate_schedule(db, payload)
    if publish:
        active_role_ids = set(db.scalars(
            select(Role.id).where(
                Role.theater_id == payload.theater_id,
                Role.is_active.is_(True),
            )
        ))
        assigned_roles: dict[int, set[int]] = defaultdict(set)
        for assignment in payload.assignments:
            assigned_roles[assignment.performance_id].add(assignment.role_id)
        incomplete = [{
            "performance_id": performance_id,
            "missing_role_ids": sorted(active_role_ids - role_ids),
        } for performance_id, role_ids in assigned_roles.items() if role_ids != active_role_ids]
        if incomplete:
            raise IncompletePerformancesError(incomplete)
    if validation["conflicts"] and not payload.confirm_conflicts:
        raise ConflictsRequireConfirmation(validation["conflicts"])
    batch = db.scalar(
        select(WeeklyBatch)
        .where(WeeklyBatch.theater_id == payload.theater_id, WeeklyBatch.week_start == payload.week_start)
        .with_for_update()
    )
    current_version = batch.version if batch else 0
    if payload.expected_version is not None and payload.expected_version != current_version:
        raise ScheduleVersionConflict(current_version)
    if batch is None:
        batch = WeeklyBatch(theater_id=payload.theater_id, week_start=payload.week_start, version=0)
        db.add(batch)
        db.flush()
    db.execute(delete(ScheduleAssignment).where(ScheduleAssignment.weekly_batch_id == batch.id))
    conflict_codes: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for conflict in validation["conflicts"]:
        conflict_codes[(conflict["performance_id"], conflict["role_id"], conflict["actor_id"])].append(conflict["code"])
    for row in payload.assignments:
        codes = conflict_codes[(row.performance_id, row.role_id, row.actor_id)]
        db.add(ScheduleAssignment(
            weekly_batch_id=batch.id, performance_id=row.performance_id, role_id=row.role_id,
            actor_id=row.actor_id, source=row.source, conflict_codes=codes,
            requires_approval=bool(codes), approved=bool(codes and payload.confirm_conflicts),
        ))
    batch.version = current_version + 1
    batch.updated_at = datetime.utcnow()
    batch.status = BatchStatus.SCHEDULED if publish else BatchStatus.READY
    batch.published_at = datetime.utcnow() if publish else None
    db.commit()
    return get_workspace(db, payload.theater_id, payload.week_start)
