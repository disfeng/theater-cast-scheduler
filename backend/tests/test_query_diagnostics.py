import logging
import time

from sqlalchemy import create_engine, event, text

from app.services.query_diagnostics import (
    PlanExpectation,
    evaluate_explain_rows,
    install_slow_query_monitor,
)


def test_explain_plan_accepts_expected_index_without_expensive_extra():
    finding = evaluate_explain_rows(
        "entitlement_inventory",
        [
            {
                "table": "entitlement_items",
                "type": "ref",
                "key": "ix_entitlement_items_theater_owner_status",
                "rows": 8,
                "Extra": "Using where",
            }
        ],
        PlanExpectation(expected_indexes=frozenset({"ix_entitlement_items_theater_owner_status"})),
    )

    assert finding.healthy is True
    assert finding.issues == ()
    assert finding.estimated_rows == 8


def test_explain_plan_rejects_full_table_scan():
    finding = evaluate_explain_rows(
        "leave_review",
        [{"table": "leave_application_days", "type": "ALL", "key": None, "rows": 900}],
        PlanExpectation(expected_indexes=frozenset({"ix_leave_days_status_date"})),
    )

    assert finding.healthy is False
    assert "full_table_scan:leave_application_days" in finding.issues
    assert "missing_expected_index" in finding.issues


def test_explain_plan_rejects_filesort_case_insensitively():
    finding = evaluate_explain_rows(
        "performance_month",
        [
            {
                "table": "performances",
                "type": "range",
                "key": "ix_performances_theater_date_status",
                "rows": 120,
                "Extra": "Using index condition; Using FILESORT",
            }
        ],
        PlanExpectation(
            expected_indexes=frozenset({"ix_performances_theater_date_status"}),
            reject_filesort=True,
        ),
    )

    assert finding.healthy is False
    assert finding.issues == ("filesort:performances",)


def test_explain_plan_allows_optimizer_choice_for_tiny_table():
    finding = evaluate_explain_rows(
        "inventory",
        [{"table": "entitlement_items", "type": "ref", "key": "short_index", "rows": 2}],
        PlanExpectation(expected_indexes=frozenset({"composite_index"})),
    )

    assert finding.healthy is True


def test_runtime_slow_query_monitor_logs_statement_without_parameters(caplog):
    engine = create_engine("sqlite://")
    install_slow_query_monitor(engine, threshold_ms=1)

    @event.listens_for(engine, "before_cursor_execute")
    def make_query_slow(conn, cursor, statement, parameters, context, executemany):
        time.sleep(0.003)

    with caplog.at_level(logging.WARNING, logger="app.slow_query"):
        with engine.connect() as connection:
            connection.execute(text("SELECT :secret"), {"secret": "do-not-log"})

    assert "slow_query" in caplog.text
    assert "SELECT ?" in caplog.text
    assert "do-not-log" not in caplog.text
