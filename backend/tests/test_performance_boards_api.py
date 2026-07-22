from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    AiParserSettingsAudit,
    BoardDraftItem,
    Performance,
    PerformanceBoard,
    PerformanceBoardRevision,
    PlayerProfile,
    Theater,
    TheaterSlot,
    User,
)
from app.models.enums import BoardChangeType, UserRole
from app.services.auth import create_access_token
import app.api.routes.admin_performance_boards as board_routes
import app.services.performance_boards as board_service
from app.core.config import settings
from app.services.ai_parser import AiParserError, ParsedBoardPayload


def _client_and_performance(db_session):
    user = User(email="board-admin@example.com", password_hash="test", role=UserRole.ADMIN)
    theater = Theater(name="信息板剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 9, 1),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    db_session.add_all([user, performance])
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    client.headers["Authorization"] = (
        f"Bearer {create_access_token(user.email, 'admin', user_id=user.id, token_version=user.token_version)}"
    )
    return client, performance


def test_board_revision_review_activation_history_and_rollback_api(db_session):
    client, performance = _client_and_performance(db_session)
    try:
        created = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息\n【昭昭】长离（恋）：Jennifer-14-3"},
        )
        assert created.status_code == 200
        revision = created.json()
        item_shape = revision["draft_items"][0]
        assert {
            "actor_name_raw",
            "role_name_raw",
            "relation_label",
            "theater_visit_ordinal",
            "character_visit_ordinal",
            "matched_player_id",
            "actor_id",
            "role_id",
            "note",
            "candidates",
            "confidence",
            "removal_lifecycle_confirmed",
        } <= item_shape.keys()
        assert revision["revision_number"] == 1
        item_id = revision["draft_items"][0]["id"]
        assert (
            client.patch(
                f"/admin/board-draft-items/{item_id}", json={"player_name": "Jennifer Corrected"}
            ).status_code
            == 200
        )
        assert (
            client.post(f"/admin/board-draft-items/{item_id}/confirm", json={}).status_code == 200
        )
        assert client.post(f"/admin/board-revisions/{revision['id']}/activate").status_code == 200

        board = client.get(f"/admin/performances/{performance.id}/board")
        assert board.status_code == 200
        assert board.json()["current_revision_id"] == revision["id"]
        assert client.get(f"/admin/board-revisions/{revision['id']}").status_code == 200

        rolled = client.post(f"/admin/board-revisions/{revision['id']}/rollback")
        assert rolled.status_code == 200
        assert rolled.json()["revision_number"] == 2
        assert rolled.json()["raw_text"] == revision["raw_text"]
        assert rolled.json()["rollback_source_revision_id"] == revision["id"]
        assert rolled.json()["draft_items"][0]["player_name"] == "Jennifer Corrected"
    finally:
        app.dependency_overrides.clear()


def test_ai_settings_authorization_audit_and_connection_do_not_create_board_data(
    db_session, monkeypatch
):
    client, _ = _client_and_performance(db_session)
    monkeypatch.setattr(settings, "settings_encryption_key", "audit-test-key")
    monkeypatch.setattr(settings, "ai_provider_allowed_hosts", "provider.example")
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]
    )
    anonymous = TestClient(app).put("/admin/system-settings/ai-parser", json={})
    assert anonymous.status_code == 401
    actor_user = User(email="actor@example.com", password_hash="test", role=UserRole.ACTOR)
    db_session.add(actor_user)
    db_session.commit()
    actor = TestClient(app)
    actor.headers["Authorization"] = (
        f"Bearer {create_access_token(actor_user.email, 'actor', user_id=actor_user.id, token_version=actor_user.token_version)}"
    )
    assert actor.get("/admin/system-settings/ai-parser").status_code == 403
    payload = {
        "enabled": True,
        "endpoint": "https://provider.example/v1",
        "api_key": "secret-not-audited",
        "model_name": "model-a",
        "timeout_seconds": 20,
    }
    assert client.put("/admin/system-settings/ai-parser", json=payload).status_code == 200
    audit = db_session.query(AiParserSettingsAudit).one()
    assert audit.action == "settings_update" and audit.key_replaced is True
    assert "secret-not-audited" not in str(audit.__dict__)
    before = tuple(
        db_session.query(model).count()
        for model in (PerformanceBoard, PerformanceBoardRevision, BoardDraftItem)
    )

    class FakeParser:
        def __init__(self, **kwargs):
            pass

        async def parse(self, *args):
            return ParsedBoardPayload(players=[], wishes=[], designations=[], unresolved_lines=[])

    monkeypatch.setattr(board_routes, "OpenAICompatibleBoardParser", FakeParser)
    tested = client.post("/admin/system-settings/ai-parser/test")
    assert tested.status_code == 200 and tested.json()["ok"] is True
    assert before == tuple(
        db_session.query(model).count()
        for model in (PerformanceBoard, PerformanceBoardRevision, BoardDraftItem)
    )
    assert db_session.query(AiParserSettingsAudit).count() == 2

    class FailingParser(FakeParser):
        async def parse(self, *args):
            raise AiParserError("sanitized")

    monkeypatch.setattr(board_routes, "OpenAICompatibleBoardParser", FailingParser)
    failed = client.post("/admin/system-settings/ai-parser/test")
    assert failed.status_code == 200 and failed.json() == {
        "ok": False,
        "message": "connection_failed",
    }
    assert before == tuple(
        db_session.query(model).count()
        for model in (PerformanceBoard, PerformanceBoardRevision, BoardDraftItem)
    )
    assert db_session.query(AiParserSettingsAudit).count() == 3
    assert "secret-not-audited" not in str(
        [row.__dict__ for row in db_session.query(AiParserSettingsAudit)]
    )
    app.dependency_overrides.clear()


def test_ambiguous_candidates_are_typed_player_descriptors(db_session, monkeypatch):
    client, performance = _client_and_performance(db_session)
    first = PlayerProfile(display_name="双生甲", normalized_name="one")
    second = PlayerProfile(display_name="双生乙", normalized_name="two")
    db_session.add_all([first, second])
    db_session.commit()
    monkeypatch.setattr(board_service, "_exact_match_players", lambda *_: [first, second])
    try:
        revision = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息\n【昭昭】长离：shared"},
        ).json()
        assert revision["draft_items"][0]["candidates"] == [
            {
                "field": "matched_player_id",
                "id": revision["draft_items"][0]["candidates"][0]["id"],
                "label": "双生甲",
            },
            {
                "field": "matched_player_id",
                "id": revision["draft_items"][0]["candidates"][1]["id"],
                "label": "双生乙",
            },
        ]
    finally:
        app.dependency_overrides.clear()


def test_bulk_confirm_never_confirms_removed_and_removed_requires_lifecycle_ack(db_session):
    client, performance = _client_and_performance(db_session)
    try:
        revision = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息\n【A】长离：One"},
        ).json()
        item = db_session.get(BoardDraftItem, revision["draft_items"][0]["id"])
        item.change_type = BoardChangeType.REMOVED
        db_session.commit()
        bulk = client.post(f"/admin/board-revisions/{revision['id']}/confirm-valid")
        assert bulk.status_code == 200
        assert bulk.json()["draft_items"][0]["confirmed_at"] is None
        rejected = client.post(f"/admin/board-draft-items/{item.id}/confirm", json={})
        assert rejected.status_code == 409
        assert rejected.json()["detail"] == "removal_lifecycle_pending"
        accepted = client.post(
            f"/admin/board-draft-items/{item.id}/confirm",
            json={"removal_lifecycle_confirmed": True},
        )
        assert accepted.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_board_api_requires_concrete_performance_and_admin_auth(db_session):
    unauthenticated = TestClient(app).post(
        "/admin/performances/999/board/revisions", json={"raw_text": "x"}
    )
    assert unauthenticated.status_code == 401
    client, _ = _client_and_performance(db_session)
    try:
        missing = client.post("/admin/performances/999/board/revisions", json={"raw_text": "x"})
        assert missing.status_code == 404
        assert missing.json()["detail"] == "performance_not_found"
    finally:
        app.dependency_overrides.clear()


def test_board_raw_draft_rejects_token_operator_not_in_database(db_session):
    theater = Theater(name="草稿剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 9, 2),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    db_session.add(performance)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token('admin@example.com', 'admin')}"
    try:
        response = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "无法解析也要保留的原文", "parse_with_ai": False},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_board_item_rejects_admin_token_user_not_in_database(db_session):
    theater = Theater(name="确认剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 9, 3),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    db_session.add_all([performance, player])
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token('admin@example.com', 'admin')}"
    try:
        response = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息", "parse_with_ai": False},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_bulk_confirm_rolls_back_all_items_when_later_validation_fails(db_session):
    client, performance = _client_and_performance(db_session)
    try:
        revision = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息\n【A】长离：One\n【B】长离：Two"},
        ).json()
        second_id = revision["draft_items"][1]["id"]
        assert (
            client.patch(
                f"/admin/board-draft-items/{second_id}", json={"matched_player_id": 999999}
            ).status_code
            == 200
        )

        response = client.post(f"/admin/board-revisions/{revision['id']}/confirm-valid")
        assert response.status_code == 409
        assert response.json()["detail"] == "player_not_found"
        refreshed = client.get(f"/admin/board-revisions/{revision['id']}").json()
        assert [item["confirmed_at"] for item in refreshed["draft_items"]] == [None, None]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("error", "status"), [(LookupError("missing_child"), 404), (ValueError("invalid_input"), 422)]
)
def test_confirm_valid_maps_missing_and_invalid_errors_consistently(
    db_session, monkeypatch, error, status
):
    client, performance = _client_and_performance(db_session)
    try:
        revision = client.post(
            f"/admin/performances/{performance.id}/board/revisions",
            json={"raw_text": "#玩家信息\n【A】长离：One"},
        ).json()

        def fail(*_args, **_kwargs):
            raise error

        monkeypatch.setattr(board_routes, "confirm_board_item", fail)
        response = client.post(f"/admin/board-revisions/{revision['id']}/confirm-valid")
        assert response.status_code == status
        assert response.json()["detail"] == str(error)
    finally:
        app.dependency_overrides.clear()
