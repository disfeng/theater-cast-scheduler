"""Recommendation commands for weekly scheduling."""

from collections import Counter

from sqlalchemy import false, select
from sqlalchemy.orm import Session


from app.models.entities import (
    Designation,
    Wish,
)
from app.schemas.weekly_scheduling import (
    AssignmentInput,
    ScheduleMutationRequest,
)


from app.services.weekly_scheduling import (
    _designation_priority,
    _inject_locked,
    get_workspace,
    validate_schedule,
)


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
        key=lambda row: (-_designation_priority(db, row), row.submitted_at, row.id),
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
            -_designation_priority(db, row)
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
                -_designation_priority(db, designation_match)
                if (
                    designation_match := matching_designation(
                        actor["id"], slot["role_id"], slot["performance_id"]
                    )
                )
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


__all__ = ["recommend_schedule"]
