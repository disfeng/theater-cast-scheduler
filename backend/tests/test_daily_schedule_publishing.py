from datetime import date

from app.models.entities import PublishedCastAssignment
from test_weekly_scheduling_api import _client, _seed_workspace


def _assignments(actors, roles, performances):
    return [
        {
            "performance_id": performance.id,
            "role_id": role.id,
            "actor_id": actors[index % len(actors)].id,
            "source": "manual",
        }
        for performance in performances
        for index, role in enumerate(roles)
    ]


def test_publish_day_creates_only_target_date_snapshot(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    try:
        saved = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": _assignments(actors, roles, performances),
                "confirm_conflicts": True,
            },
        )
        assert saved.status_code == 200

        published = client.post(
            "/admin/weekly-schedules/publish-day",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "performance_date": "2026-12-31",
                "expected_version": saved.json()["version"],
                "idempotency_key": "publish-day-2026-12-31",
            },
        )

        assert published.status_code == 200, published.text
        assert published.json()["published_performance_ids"] == [performances[0].id]
        snapshots = db_session.query(PublishedCastAssignment).all()
        assert {row.performance_id for row in snapshots} == {performances[0].id}
        workspace = published.json()["workspace"]
        first = next(row for row in workspace["performances"] if row["id"] == performances[0].id)
        second = next(row for row in workspace["performances"] if row["id"] == performances[1].id)
        assert first["publication_status"] == "published"
        assert second["publication_status"] == "draft"
    finally:
        from app.main import app

        app.dependency_overrides.clear()


def test_republish_changed_day_requires_confirmation(db_session):
    theater, actors, roles, performances = _seed_workspace(db_session)
    client, headers = _client(db_session)
    try:
        initial = _assignments(actors, roles, performances)
        saved = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": 0,
                "assignments": initial,
                "confirm_conflicts": True,
            },
        ).json()
        first_publish = client.post(
            "/admin/weekly-schedules/publish-day",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "performance_date": "2026-12-31",
                "expected_version": saved["version"],
                "idempotency_key": "first-publish",
            },
        )
        assert first_publish.status_code == 200

        changed = [dict(row) for row in initial]
        changed[0]["actor_id"] = actors[1].id
        draft = client.put(
            "/admin/weekly-schedules/draft",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "expected_version": first_publish.json()["workspace"]["version"],
                "assignments": changed,
                "confirm_conflicts": True,
            },
        )
        assert draft.status_code == 200

        rejected = client.post(
            "/admin/weekly-schedules/publish-day",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "performance_date": "2026-12-31",
                "expected_version": draft.json()["version"],
                "idempotency_key": "changed-publish",
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "republish_confirmation_required"
        assert rejected.json()["detail"]["changed"] == 1

        confirmed = client.post(
            "/admin/weekly-schedules/publish-day",
            headers=headers,
            json={
                "theater_id": theater.id,
                "week_start": "2026-12-28",
                "performance_date": "2026-12-31",
                "expected_version": draft.json()["version"],
                "idempotency_key": "changed-publish-confirmed",
                "confirm_republish": True,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["publication_version"] == 2
    finally:
        from app.main import app

        app.dependency_overrides.clear()
