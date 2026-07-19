from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.api.deps import get_db
from app.main import app
from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    PlayerAlias,
    PlayerProfile,
    Theater,
    User,
)
from app.models.enums import (
    EntitlementEventType,
    GrantBatchStatus,
    EntitlementItemStatus,
    PlayerStatus,
    UserRole,
)
from app.services.auth import create_access_token
from app.services.entitlements import (
    entitlement_reconciliation,
    normalize_player_name,
    reconciliation_drill,
)


def _client(db_session):
    db_session.add(User(email="admin@example.com", password_hash="test", role=UserRole.ADMIN))
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token('admin@example.com', 'admin')}"
    return client


def test_theater_item_definition_crud_and_category_validation(db_session):
    client = _client(db_session)
    theater = Theater(name="权益配置剧场")
    db_session.add(theater)
    db_session.commit()
    try:
        invalid = client.post(
            f"/admin/theaters/{theater.id}/entitlement-item-types",
            json={
                "code": "drink",
                "display_name": "饮品券",
                "category": "general",
                "designation_type": "universal",
                "priority": 0,
                "default_validity_days": 30,
                "color": "#409eff",
                "is_active": True,
                "sort_order": 0,
            },
        )
        assert invalid.status_code == 422

        created = client.post(
            f"/admin/theaters/{theater.id}/entitlement-item-types",
            json={
                "code": "drink",
                "display_name": "饮品券",
                "category": "general",
                "priority": 0,
                "default_validity_days": 30,
                "color": "#409eff",
                "is_active": True,
                "sort_order": 0,
            },
        )
        assert created.status_code == 200
        assert created.json()["theater_id"] == theater.id
        assert client.get(
            f"/admin/theaters/{theater.id}/entitlement-item-types"
        ).json()[0]["display_name"] == "饮品券"

        defaults = client.post(
            f"/admin/theaters/{theater.id}/entitlement-item-types/default-designations"
        )
        assert defaults.status_code == 200
        assert [(row["designation_type"], row["priority"]) for row in defaults.json()] == [
            ("universal", 300),
            ("top_three", 200),
            ("paired", 100),
        ]

        player = PlayerProfile(display_name="发放玩家", normalized_name="发放玩家")
        db_session.add(player)
        db_session.commit()
        batch = client.post(
            f"/admin/theaters/{theater.id}/entitlement-grant-batches",
            json={
                "source_type": "campaign",
                "source_label": "开业活动",
                "grant_date": "2026-07-19",
                "default_expires_at": "2026-10-19T23:59:59",
                "items": [
                    {
                        "player_id": player.id,
                        "item_type_id": created.json()["id"],
                        "quantity": 2,
                    }
                ],
            },
        )
        assert batch.status_code == 200
        confirmed = client.post(
            f"/admin/theaters/{theater.id}/entitlement-grant-batches/{batch.json()['id']}/confirm",
            headers={"Idempotency-Key": "grant-config-test"},
        )
        assert confirmed.status_code == 200
        repeated = client.post(
            f"/admin/theaters/{theater.id}/entitlement-grant-batches/{batch.json()['id']}/confirm",
            headers={"Idempotency-Key": "grant-config-test"},
        )
        assert repeated.status_code == 200
        inventory = client.get(
            f"/admin/theaters/{theater.id}/players/{player.id}/inventory"
        )
        assert len(inventory.json()["items"]) == 2

        matches = client.post(
            f"/admin/theaters/{theater.id}/entitlement-grant-player-matches",
            json={"names": ["发放玩家", "待确认新玩家", "发放玩家"]},
        )
        assert matches.status_code == 200
        assert [row["raw_name"] for row in matches.json()] == ["发放玩家", "待确认新玩家"]
        assert matches.json()[1]["player"]["status"] == "provisional"
    finally:
        app.dependency_overrides.clear()


def test_player_search_create_alias_and_merge(db_session):
    client = _client(db_session)
    try:
        created = client.post("/admin/player-profiles", json={"display_name": " Alice Smith "})
        assert created.status_code == 200
        alice_id = created.json()["player"]["id"]
        client.patch(f"/admin/player-profiles/{alice_id}", json={"status": "active"})
        alias = client.post(f"/admin/player-profiles/{alice_id}/aliases", json={"alias": "A Smith"})
        assert alias.status_code == 200
        searched = client.get("/admin/player-profiles", params={"q": "a smith"})
        assert searched.status_code == 200
        assert searched.json()[0]["id"] == alice_id

        bob = client.post("/admin/player-profiles", json={"display_name": "Bob"}).json()["player"]
        merged = client.post(
            f"/admin/player-profiles/{alice_id}/merge", json={"source_player_id": bob["id"]}
        )
        assert merged.status_code == 200
        assert db_session.get(PlayerProfile, bob["id"]).status == PlayerStatus.MERGED
    finally:
        app.dependency_overrides.clear()


def test_provisional_player_confirm_patch_batch_and_item_detail(db_session):
    client = _client(db_session)
    try:
        created = client.post("/admin/player-profiles", json={"display_name": " New Player "})
        assert created.status_code == 200
        player_id = created.json()["player"]["id"]
        assert created.json()["player"]["status"] == "provisional"
        assert (
            client.patch(
                f"/admin/player-profiles/{player_id}", json={"status": "active"}
            ).status_code
            == 200
        )

        kind = EntitlementItemType(
            code="universal", display_name="Universal", priority=1, default_validity_months=3
        )
        db_session.add(kind)
        db_session.commit()
        batch = client.post(
            "/admin/entitlement-grant-batches",
            json={
                "source_month": "2026-07-01",
                "source_label": "July",
                "items": [{"player_id": player_id, "item_type_id": kind.id}],
            },
        ).json()
        patched = client.patch(
            f"/admin/entitlement-grant-batches/{batch['id']}",
            json={
                "source_month": "2026-07-01",
                "source_label": "July corrected",
                "items": batch["draft_items"],
            },
        )
        assert patched.status_code == 200
        client.post(f"/admin/entitlement-grant-batches/{batch['id']}/confirm")
        item_id = client.get(f"/admin/players/{player_id}/inventory").json()["items"][0]["id"]
        assert client.get(f"/admin/entitlement-items/{item_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_ambiguous_and_blank_inputs_have_stable_errors(db_session):
    client = _client(db_session)
    try:
        db_session.add_all(
            [
                PlayerProfile(display_name="Alice One", normalized_name="aliceone"),
                PlayerProfile(display_name="Alice Two", normalized_name="alicetwo"),
            ]
        )
        db_session.commit()
        ambiguous = client.post("/admin/player-profiles", json={"display_name": "alice"})
        assert ambiguous.status_code == 409
        assert ambiguous.json()["detail"] == "player_match_ambiguous"
        assert (
            client.post("/admin/player-profiles", json={"display_name": "   "}).status_code == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_item_type_batch_crud_confirm_and_inventory(db_session):
    client = _client(db_session)
    try:
        player = PlayerProfile(display_name="Alice", normalized_name=normalize_player_name("Alice"))
        db_session.add(player)
        db_session.commit()
        item_type = EntitlementItemType(
            code="universal", display_name="VIP", priority=1, default_validity_months=3
        )
        db_session.add(item_type)
        db_session.commit()
        batch = client.post(
            "/admin/entitlement-grant-batches",
            json={
                "source_month": "2026-07-01",
                "source_label": "July",
                "title": "July VIP",
                "items": [{"player_id": player.id, "item_type_id": item_type.id, "quantity": 2}],
            },
        )
        assert batch.status_code == 200
        assert (
            client.get(f"/admin/entitlement-grant-batches/{batch.json()['id']}").status_code == 200
        )
        confirmed = client.post(f"/admin/entitlement-grant-batches/{batch.json()['id']}/confirm")
        assert confirmed.status_code == 200
        inventory = client.get(f"/admin/players/{player.id}/inventory")
        assert inventory.status_code == 200
        assert len(inventory.json()["items"]) == 2
        assert {
            row.operator_user_id for row in db_session.scalars(select(EntitlementLedgerEntry)).all()
        } == {db_session.scalar(select(User).where(User.email == "admin@example.com")).id}
        rejected = client.patch(
            f"/admin/entitlement-grant-batches/{batch.json()['id']}",
            json={"source_month": "2026-07-01", "source_label": "changed", "items": []},
        )
        assert rejected.status_code == 409
        assert (
            client.delete(f"/admin/entitlement-grant-batches/{batch.json()['id']}").status_code
            == 409
        )
        assert (
            client.post(
                "/admin/entitlement-item-types",
                json={
                    "code": "custom",
                    "display_name": "Custom",
                    "priority": 9,
                    "default_validity_months": 3,
                },
            ).status_code
            == 405
        )
    finally:
        app.dependency_overrides.clear()


def test_merge_moves_draft_references_to_active_target(db_session):
    client = _client(db_session)
    try:
        target = PlayerProfile(
            display_name="Target", normalized_name="target", status=PlayerStatus.ACTIVE
        )
        source = PlayerProfile(
            display_name="Source", normalized_name="source", status=PlayerStatus.ACTIVE
        )
        kind = EntitlementItemType(
            code="universal", display_name="Universal", priority=1, default_validity_months=3
        )
        batch = EntitlementGrantBatch(source_month=date(2026, 7, 1), source_label="July")
        db_session.add_all([target, source, kind, batch])
        db_session.flush()
        draft = EntitlementGrantDraftItem(
            batch_id=batch.id, player_id=source.id, item_type_id=kind.id
        )
        db_session.add(draft)
        db_session.commit()
        response = client.post(
            f"/admin/player-profiles/{target.id}/merge", json={"source_player_id": source.id}
        )
        assert response.status_code == 200
        db_session.refresh(draft)
        assert draft.player_id == target.id
        assert db_session.get(PlayerProfile, source.id).merged_into_id == target.id
    finally:
        app.dependency_overrides.clear()


def test_missing_persisted_operator_is_rejected(db_session):
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        client = TestClient(app)
        token = create_access_token("ghost@example.com", "admin")
        response = client.post(
            "/admin/entitlement-grant-batches",
            headers={"Authorization": f"Bearer {token}"},
            json={"source_month": "2026-07-01", "source_label": "July", "items": []},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "operator_user_not_found"
    finally:
        app.dependency_overrides.clear()


def test_player_name_claims_conflict_both_directions_and_follow_rename_merge(db_session):
    client = _client(db_session)
    try:
        first = client.post("/admin/player-profiles", json={"display_name": "Alice"}).json()[
            "player"
        ]
        second = client.post("/admin/player-profiles", json={"display_name": "Bob"}).json()[
            "player"
        ]
        assert (
            client.post(
                f"/admin/player-profiles/{second['id']}/aliases", json={"alias": " Alice "}
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/admin/player-profiles/{first['id']}/aliases", json={"alias": "Bobby"}
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/admin/player-profiles/{second['id']}", json={"display_name": " Bobby "}
            ).status_code
            == 409
        )

        renamed = client.patch(
            f"/admin/player-profiles/{first['id']}", json={"display_name": " Alicia "}
        )
        assert renamed.status_code == 200
        assert (
            client.post(
                f"/admin/player-profiles/{second['id']}/aliases", json={"alias": "Alice"}
            ).status_code
            == 200
        )

        client.patch(f"/admin/player-profiles/{first['id']}", json={"status": "active"})
        merged = client.post(
            f"/admin/player-profiles/{first['id']}/merge", json={"source_player_id": second["id"]}
        )
        assert merged.status_code == 200
        claims = db_session.scalars(
            select(PlayerAlias).where(PlayerAlias.player_id == first["id"])
        ).all()
        assert {claim.normalized_alias for claim in claims} >= {"alicia", "bobby", "alice", "bob"}
    finally:
        app.dependency_overrides.clear()


def test_string_boundaries_return_422(db_session):
    client = _client(db_session)
    try:
        assert (
            client.post("/admin/player-profiles", json={"display_name": "x" * 121}).status_code
            == 422
        )
        player = PlayerProfile(display_name="Alice", normalized_name="alice")
        kind = EntitlementItemType(
            code="universal", display_name="Universal", priority=1, default_validity_months=3
        )
        db_session.add_all([player, kind])
        db_session.commit()
        assert (
            client.post(
                f"/admin/player-profiles/{player.id}/aliases", json={"alias": "x" * 121}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/admin/entitlement-item-types/{kind.id}", json={"display_name": "   "}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/admin/entitlement-grant-batches",
                json={"source_month": "2026-07-01", "source_label": "x" * 121, "items": []},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/admin/entitlement-grant-batches",
                json={
                    "source_month": "2026-07-01",
                    "source_label": "July",
                    "items": [
                        {"player_id": player.id, "item_type_id": kind.id, "source_label": "   "}
                    ],
                },
            ).status_code
            == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_merged_profiles_reject_mutation_and_merge_chains(db_session):
    client = _client(db_session)
    try:
        target = PlayerProfile(
            display_name="Target", normalized_name="target", status=PlayerStatus.ACTIVE
        )
        source = PlayerProfile(
            display_name="Source", normalized_name="source", status=PlayerStatus.MERGED
        )
        db_session.add_all([target, source])
        db_session.flush()
        source.merged_into_id = target.id
        db_session.commit()
        assert (
            client.patch(
                f"/admin/player-profiles/{source.id}", json={"display_name": "Revived"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/admin/player-profiles/{source.id}/aliases", json={"alias": "Revived"}
            ).status_code
            == 409
        )
        chain = client.post(
            f"/admin/player-profiles/{target.id}/merge", json={"source_player_id": source.id}
        )
        assert chain.status_code == 409
        assert chain.json()["detail"] == "player_merge_invalid_status"
    finally:
        app.dependency_overrides.clear()


def test_extension_void_restore_adjustment_and_stable_errors(db_session):
    client = _client(db_session)
    try:
        player = PlayerProfile(display_name="Alice", normalized_name="alice")
        kind = EntitlementItemType(
            code="vip", display_name="VIP", priority=1, default_validity_months=3
        )
        db_session.add_all([player, kind])
        db_session.commit()
        expiry = datetime.utcnow() + timedelta(days=10)
        item = EntitlementItem(
            serial_number="DT-202607-0001",
            owner_id=player.id,
            item_type_id=kind.id,
            source_month=date(2026, 7, 1),
            source_label="July",
            granted_at=datetime.utcnow(),
            expires_at=expiry,
            status=EntitlementItemStatus.AVAILABLE,
        )
        db_session.add(item)
        db_session.commit()

        extended = client.post(
            f"/admin/entitlement-items/{item.id}/extend",
            json={"expires_at": (expiry + timedelta(days=10)).isoformat(), "reason": "support"},
        )
        assert extended.status_code == 200
        assert (
            client.post(
                f"/admin/entitlement-items/{item.id}/void", json={"reason": "mistake"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/admin/entitlement-items/{item.id}/restore", json={"reason": "approved"}
            ).status_code
            == 200
        )
        adjusted = client.post(
            f"/admin/entitlement-items/{item.id}/adjust",
            json={"source_label": "corrected", "notes": "audit", "reason": "correction"},
        )
        assert adjusted.status_code == 200
        duplicate_void = client.post(
            f"/admin/entitlement-items/{item.id}/restore", json={"reason": "again"}
        )
        assert duplicate_void.status_code == 409
        assert duplicate_void.json()["detail"] == "entitlement_not_revoked"
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_groups_and_drills_down_to_items_and_ledgers(db_session):
    client = _client(db_session)
    try:
        player = PlayerProfile(display_name="Audit Player", normalized_name="auditplayer")
        kind = EntitlementItemType(
            code="universal",
            display_name="Universal",
            priority=1,
            default_validity_months=3,
        )
        db_session.add_all([player, kind])
        db_session.commit()
        batch = client.post(
            "/admin/entitlement-grant-batches",
            json={
                "source_month": "2026-07-01",
                "source_label": "July",
                "items": [{"player_id": player.id, "item_type_id": kind.id, "quantity": 2}],
            },
        ).json()
        assert (
            client.post(f"/admin/entitlement-grant-batches/{batch['id']}/confirm").status_code
            == 200
        )

        response = client.get("/admin/entitlements/reconciliation")
        assert response.status_code == 200
        payload = response.json()
        row = payload["rows"][0]
        assert row["item_count"] == 2
        assert row["drill_down_filter"] == {
            "item_type": "universal",
            "source_month": "2026-07-01",
            "source_label": "July",
            "player_id": player.id,
            "status": "available",
        }
        assert payload["filtered_totals"]["available"] == 2
        assert payload["global_totals"]["available"] == 2
        assert payload["anomaly_count"] == 0
        items = client.get(
            "/admin/entitlements/reconciliation/drill",
            params={
                "kind": "items",
                **row["drill_down_filter"],
            },
        ).json()
        ledgers = client.get(
            "/admin/entitlements/reconciliation/drill",
            params={
                "kind": "ledgers",
                **row["drill_down_filter"],
            },
        ).json()
        assert items["total"] == len(items["records"]) == 2
        assert ledgers["total"] == len(ledgers["records"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_reports_batch_ledger_and_expiry_anomalies(db_session):
    client = _client(db_session)
    try:
        player = PlayerProfile(display_name="Mismatch", normalized_name="mismatch")
        kind = EntitlementItemType(
            code="paired",
            display_name="Paired",
            priority=3,
            default_validity_months=3,
        )
        batch = EntitlementGrantBatch(
            source_month=date(2026, 7, 1),
            source_label="Broken",
            status=GrantBatchStatus.GRANTED,
        )
        db_session.add_all([player, kind, batch])
        db_session.flush()
        item = EntitlementItem(
            serial_number="AUDIT-BROKEN",
            owner_id=player.id,
            item_type_id=kind.id,
            grant_batch_id=batch.id,
            source_month=date(2026, 7, 1),
            source_label="Broken",
            granted_at=datetime.utcnow(),
            expires_at=datetime.utcnow() - timedelta(days=1),
            status=EntitlementItemStatus.AVAILABLE,
        )
        db_session.add(item)
        db_session.commit()

        payload = client.get("/admin/entitlements/reconciliation?expiry=expired").json()
        details = client.get(
            "/admin/entitlements/reconciliation/drill?kind=anomalies&expiry=expired"
        ).json()
        codes = {row["code"] for row in details["records"]}
        assert {
            "grant_batch_total_mismatch",
            "missing_grant_ledger",
            "missing_item_ledger",
            "available_item_expired",
        } <= codes
        assert payload["filtered_totals"]["available"] == 1
        assert payload["global_totals"]["available"] == 1
        invalid = client.get("/admin/entitlements/reconciliation?expiry=soon")
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == "entitlement_expiry_filter_invalid"
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_detects_missing_duplicate_and_invalid_grants_per_item(db_session):
    client = _client(db_session)
    try:
        player = PlayerProfile(display_name="Cardinality", normalized_name="cardinality")
        kind = EntitlementItemType(
            code="universal", display_name="Universal", priority=1, default_validity_months=3
        )
        db_session.add_all([player, kind])
        db_session.flush()
        common = {
            "owner_id": player.id,
            "item_type_id": kind.id,
            "source_month": date(2026, 7, 1),
            "source_label": "audit",
            "granted_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=30),
        }
        missing = EntitlementItem(serial_number="MISS", **common)
        duplicate = EntitlementItem(serial_number="DUP", **common)
        invalid = EntitlementItem(serial_number="BAD", **common)
        db_session.add_all([missing, duplicate, invalid])
        db_session.flush()
        db_session.add_all(
            [
                EntitlementLedgerEntry(
                    item_id=duplicate.id,
                    event_type=EntitlementEventType.GRANTED,
                    from_status=None,
                    to_status=EntitlementItemStatus.AVAILABLE,
                ),
                EntitlementLedgerEntry(
                    item_id=duplicate.id,
                    event_type=EntitlementEventType.GRANTED,
                    from_status=None,
                    to_status=EntitlementItemStatus.AVAILABLE,
                ),
                EntitlementLedgerEntry(
                    item_id=invalid.id,
                    event_type=EntitlementEventType.GRANTED,
                    from_status=EntitlementItemStatus.RESERVED,
                    to_status=EntitlementItemStatus.CONSUMED,
                ),
            ]
        )
        db_session.commit()
        records = client.get(
            "/admin/entitlements/reconciliation/drill?kind=anomalies&limit=100"
        ).json()["records"]
        pairs = {(row["code"], tuple(row["item_ids"])) for row in records}
        assert ("missing_grant_ledger", (missing.id,)) in pairs
        assert ("duplicate_grant_ledger", (duplicate.id,)) in pairs
        assert ("invalid_grant_transition", (invalid.id,)) in pairs
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_expiry_boundaries_use_one_frozen_now(db_session):
    now = datetime(2026, 7, 17, 12, 0, 0)
    player = PlayerProfile(display_name="Boundary", normalized_name="boundary")
    kind = EntitlementItemType(
        code="paired", display_name="Paired", priority=3, default_validity_months=3
    )
    db_session.add_all([player, kind])
    db_session.flush()
    expiries = [
        now - timedelta(microseconds=1),
        now,
        now + timedelta(microseconds=1),
        now + timedelta(days=7),
        now + timedelta(days=7, microseconds=1),
        now + timedelta(days=30),
        now + timedelta(days=30, microseconds=1),
    ]
    db_session.add_all(
        [
            EntitlementItem(
                serial_number=f"BOUND-{index}",
                owner_id=player.id,
                item_type_id=kind.id,
                source_month=date(2026, 7, 1),
                source_label="boundary",
                granted_at=now,
                expires_at=expiry,
                status=EntitlementItemStatus.AVAILABLE,
            )
            for index, expiry in enumerate(expiries)
        ]
    )
    db_session.commit()
    assert (
        entitlement_reconciliation(db_session, expiry="expired", now=now)["filtered_totals"][
            "available"
        ]
        == 2
    )
    assert (
        entitlement_reconciliation(db_session, expiry="expires_within_7_days", now=now)[
            "filtered_totals"
        ]["available"]
        == 2
    )
    assert (
        entitlement_reconciliation(db_session, expiry="expires_within_30_days", now=now)[
            "filtered_totals"
        ]["available"]
        == 4
    )


def test_large_reconciliation_is_fixed_query_count_and_bounded(db_session):
    now = datetime(2026, 7, 17, 12, 0, 0)
    player = PlayerProfile(display_name="Large", normalized_name="large")
    kind = EntitlementItemType(
        code="universal", display_name="Universal", priority=1, default_validity_months=3
    )
    db_session.add_all([player, kind])
    db_session.flush()
    items = [
        EntitlementItem(
            serial_number=f"LARGE-{index:04d}",
            owner_id=player.id,
            item_type_id=kind.id,
            source_month=date(2026, 7, 1),
            source_label="large",
            granted_at=now,
            expires_at=now + timedelta(days=60),
            status=EntitlementItemStatus.AVAILABLE,
        )
        for index in range(550)
    ]
    db_session.add_all(items)
    db_session.flush()
    db_session.add_all(
        [
            EntitlementLedgerEntry(
                item_id=item.id,
                event_type=EntitlementEventType.GRANTED,
                from_status=None,
                to_status=EntitlementItemStatus.AVAILABLE,
            )
            for item in items
        ]
    )
    db_session.commit()
    db_session.expunge_all()
    count = 0

    def counted(*_):
        nonlocal count
        count += 1

    event.listen(db_session.bind, "before_cursor_execute", counted)
    try:
        summary = entitlement_reconciliation(db_session, now=now)
        summary_queries = count
        count = 0
        detail = reconciliation_drill(
            db_session, kind="items", expiry=None, limit=10, cursor=0, filters={}, now=now
        )
    finally:
        event.remove(db_session.bind, "before_cursor_execute", counted)
    assert summary["rows"][0]["item_count"] == 550
    assert summary_queries <= 6
    assert count <= 2
    assert detail["total"] == 550 and len(detail["records"]) == 10
    assert len(db_session.identity_map) <= 10
