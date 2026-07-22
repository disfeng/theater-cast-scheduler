from app.cli.query_health import QUERY_CHECKS, run_diagnostics


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.statements: list[str] = []

    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        return _Result(self.rows)


def test_query_health_uses_only_predefined_explain_statements():
    session = _Session([{"table": "performances", "type": "range", "key": "expected", "rows": 2}])
    check = QUERY_CHECKS["performance_month"]
    check = check.with_expected_indexes("expected")

    report = run_diagnostics(session, {check.name: check})

    assert report.healthy is True
    assert session.statements == [check.explain_sql]
    assert session.statements[0].startswith("EXPLAIN SELECT")
    assert "password" not in report.to_json().lower()


def test_query_health_returns_unhealthy_report_for_bad_plan():
    session = _Session([{"table": "performances", "type": "ALL", "key": None, "rows": 999}])

    report = run_diagnostics(session, {"performance_month": QUERY_CHECKS["performance_month"]})

    assert report.healthy is False
    assert report.exit_code == 1
