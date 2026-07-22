from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Iterable, Mapping

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class PlanExpectation:
    expected_indexes: frozenset[str] = frozenset()
    reject_full_scan: bool = True
    reject_filesort: bool = True
    require_expected_index_above_rows: int = 100


@dataclass(frozen=True)
class PlanFinding:
    name: str
    healthy: bool
    issues: tuple[str, ...]
    used_indexes: tuple[str, ...]
    estimated_rows: int


def evaluate_explain_rows(
    name: str,
    rows: Iterable[Mapping[str, Any]],
    expectation: PlanExpectation,
) -> PlanFinding:
    issues: list[str] = []
    used_indexes: list[str] = []
    estimated_rows = 0

    for row in rows:
        table = str(row.get("table") or "unknown")
        access_type = str(row.get("type") or "").upper()
        key = row.get("key")
        extra = str(row.get("Extra") or row.get("extra") or "").lower()
        estimated_rows += int(row.get("rows") or 0)

        if key:
            used_indexes.append(str(key))
        if expectation.reject_full_scan and access_type == "ALL":
            issues.append(f"full_table_scan:{table}")
        if expectation.reject_filesort and "filesort" in extra:
            issues.append(f"filesort:{table}")

    if (
        expectation.expected_indexes
        and estimated_rows > expectation.require_expected_index_above_rows
        and not expectation.expected_indexes.intersection(used_indexes)
    ):
        issues.append("missing_expected_index")

    return PlanFinding(
        name=name,
        healthy=not issues,
        issues=tuple(issues),
        used_indexes=tuple(dict.fromkeys(used_indexes)),
        estimated_rows=estimated_rows,
    )


def install_slow_query_monitor(
    engine: Engine,
    *,
    threshold_ms: int,
    logger: logging.Logger | None = None,
) -> None:
    """Log slow statements without parameters so production secrets stay out of logs."""
    if threshold_ms <= 0 or getattr(engine, "_slow_query_monitor_installed", False):
        return
    target_logger = logger or logging.getLogger("app.slow_query")

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_started_at = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started_at = getattr(context, "_query_started_at", None)
        if started_at is None:
            return
        duration_ms = (perf_counter() - started_at) * 1000
        if duration_ms < threshold_ms:
            return
        compact_statement = " ".join(statement.split())[:500]
        target_logger.warning(
            "slow_query duration_ms=%.2f statement=%s",
            duration_ms,
            compact_statement,
        )

    engine._slow_query_monitor_installed = True
